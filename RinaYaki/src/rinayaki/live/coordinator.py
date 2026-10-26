"""Realtime chain orchestration for live sessions.

Chain shape (latency-first):

    WASAPI loopback -> 16 kHz mono PCM -> Qwen streaming ASR (partial/final)
                    -> fast Qwen-MT translation -> subtitle sinks

Decoupling guarantees:

- Translation has its own bounded queue with the same drop-oldest policy so a
  slow LLM cannot back up the ASR feed.
- Source-only sessions do not create a translation client or worker and issue
  no translation requests. Offline refinement is a later session handoff.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
import threading
import time

from .. import cloud_asr, languages, settings as settings_module, translation
from ..guidance import Guidance
from ..billing import record as record_billing
from . import events as ev
from .capture.wasapi_loopback import WasapiLoopbackCapture
from .session import LiveSettings, SessionPaths, write_session_record, write_transcript
from .sinks.session_recorder import WaveRecorder
from .livetranslate import LiveTranslate, MODEL as LIVETRANSLATE_MODEL


class BoundedChannel:
    """FIFO with drop-oldest overflow: producers never block, order is kept."""

    def __init__(self, capacity: int, on_drop: Callable[[object], None] | None = None) -> None:
        if capacity < 1:
            raise ValueError("channel capacity must be positive")
        self._items: deque = deque()
        self._capacity = capacity
        self._lock = threading.Lock()
        self._ready = threading.Condition(self._lock)
        self._closed = False
        self._on_drop = on_drop

    def put(self, item) -> bool:
        """Returns False when an oldest item had to be dropped."""
        dropped = None
        with self._lock:
            if self._closed:
                return False
            if len(self._items) >= self._capacity:
                dropped = self._items.popleft()
            self._items.append(item)
            self._ready.notify()
        if dropped is not None:
            if self._on_drop is not None:
                self._on_drop(dropped)
            return False
        return True

    def get(self, timeout: float):
        with self._ready:
            while not self._items:
                if self._closed:
                    return None
                if not self._ready.wait(timeout):
                    return None
            return self._items.popleft()

    def close(self, *, discard: bool = False) -> None:
        with self._lock:
            self._closed = True
            if discard:
                self._items.clear()
            self._ready.notify_all()


@dataclass(frozen=True, slots=True)
class _FinalEntry:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str


class QwenStreamingAsr:
    """Live ASR over DashScope's realtime Recognition (qwen audio streaming)."""

    def __init__(
        self,
        api_key: str,
        websocket_url: str,
        *,
        source_language: str,
        on_partial: Callable[[str, int, int], None],
        on_final: Callable[[str, int, int], None],
        on_error: Callable[[str], None],
        partial_throttle_ms: int = 300,
    ) -> None:
        self._api_key = api_key
        self._websocket_url = websocket_url
        self._hints = list(languages.asr_hints(source_language))
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._throttle_ms = partial_throttle_ms
        self._recognition = None
        self._last_partial_ms = 0
        self._last_partial_text = ""

    def start(self) -> None:
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        coordinator = self

        class Callback(RecognitionCallback):
            def on_error(self, result) -> None:
                coordinator._on_error(str(getattr(result, "message", result)))

            def on_event(self, result) -> None:
                sentence = result.get_sentence()
                if not sentence:
                    return
                text = str(sentence.get("text") or "").strip()
                if not text:
                    return
                start_ms = int(sentence.get("begin_time") or 0)
                end_ms = int(sentence.get("end_time") or 0)
                if RecognitionResult.is_sentence_end(sentence):
                    coordinator._on_final(text, start_ms, end_ms)
                else:
                    coordinator.handle_partial(text, start_ms, end_ms)

        self._recognition = Recognition(
            model=cloud_asr.STREAMING_MODEL,
            format="pcm",
            sample_rate=16_000,
            language_hints=self._hints or None,
            semantic_punctuation_enabled=False,
            callback=Callback(),
        )
        import dashscope

        dashscope.api_key = self._api_key
        dashscope.base_websocket_api_url = self._websocket_url
        self._recognition.start()

    def send(self, pcm_block: bytes) -> None:
        if self._recognition is not None:
            self._recognition.send_audio_frame(pcm_block)

    def stop(self) -> None:
        if self._recognition is not None:
            try:
                self._recognition.stop()
            finally:
                self._recognition = None

    # partial handling lives here so the SDK callback thread stays minimal
    def handle_partial(self, text: str, start_ms: int, end_ms: int) -> None:
        now = time.monotonic_ns() // 1_000_000
        if text == self._last_partial_text or now - self._last_partial_ms < self._throttle_ms:
            return
        self._last_partial_ms = now
        self._last_partial_text = text
        self._on_partial(text, start_ms, end_ms)


class DryRunAsr:
    """Audio-consuming stub for ``--dry-run``: exercises the chain, calls no API."""

    name = "dry_run"

    def __init__(self) -> None:
        self.bytes_seen = 0

    def start(self) -> None:
        return None

    def send(self, pcm_block: bytes) -> None:
        self.bytes_seen += len(pcm_block)

    def stop(self) -> None:
        return None


class RealtimeCoordinator:
    def __init__(
        self,
        live: LiveSettings,
        shared: settings_module.UserSettings,
        paths: SessionPaths,
        *,
        bus: ev.EventBus,
        dry_run: bool = False,
        guidance: Guidance | None = None,
    ) -> None:
        live.public()  # validate early
        self._live = live
        self._shared = shared
        self._paths = paths
        self._bus = bus
        self._dry_run = dry_run
        self._guidance = guidance or Guidance()
        self._stop_requested = threading.Event()
        self._stopped_event = threading.Event()
        self._paused = threading.Event()
        self._started = False
        self._audio_generation = 0
        self._audio_bytes = 0
        self._lifecycle_lock = threading.RLock()
        self._segments_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._segments: list[dict] = []
        self._segment_seq = 0
        self._stats = {
            "audio_blocks": 0,
            "partials": 0,
            "finals": 0,
            "translations": 0,
            "translation_updates": 0,
            "translation_errors": 0,
            "translation_dropped": 0,
            "recording_dropped": 0,
            "recorded_audio_bytes": 0,
            "guidance_terms": 0,
        }
        self._asr: QwenStreamingAsr | None = None
        self._capture: WasapiLoopbackCapture | None = None
        self._recorder: WaveRecorder | None = None
        self._translation_queue: BoundedChannel | None = None
        self._translator_thread: threading.Thread | None = None
        self._usage: dict = {}

    @property
    def model(self) -> str:
        return LIVETRANSLATE_MODEL if self._live.uses_livetranslate else cloud_asr.STREAMING_MODEL

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._stopped_event.is_set() or self._stop_requested.is_set():
                raise RuntimeError("实时会话已经停止，不能再次启动。")
            try:
                if not self._dry_run and not self._shared.api_key:
                    raise ValueError("未配置 DASHSCOPE_API_KEY；请先在 RinaYaki 设置中完成 API 配置。")

                if self._live.translation_enabled and not self._live.uses_livetranslate and not self._dry_run:
                    translator = translation.DashScopeOpenAIClient(
                        self._shared.api_key or "dry-run",
                        self._shared.base_url,
                        minimum_interval_seconds=self._shared.minimum_interval_seconds,
                    )
                    self._translation_queue = BoundedChannel(
                        self._live.translation_queue_capacity,
                        on_drop=self._on_translation_drop,
                    )
                    self._translator_thread = threading.Thread(
                        target=self._translate_loop,
                        args=(translator,),
                        name="yaki-live-translator",
                        daemon=True,
                    )
                    self._translator_thread.start()

                if self._live.record_session:
                    self._recorder = WaveRecorder(self._paths.audio_wav)
                    self._recorder.start()

                self._start_audio()
                if self._stop_requested.is_set():
                    return
                self._started = True
                write_session_record(
                    self._paths,
                    self._live,
                    self._provenance(),
                    self.stats,
                    status="running",
                )
                self._bus.emit(ev.session_started(str(self._paths.root), self._live.public()))
            except Exception as error:
                self._bus.emit(ev.runtime_error(str(error)[:300]))
                self.stop("startup-failed")
                raise

    def _start_audio(self) -> None:
        # Each resumed ASR connection starts its clock at zero. Offset into the
        # concatenated (pause-free) recording, and reject callbacks from old runs.
        self._audio_generation += 1
        generation = self._audio_generation
        offset = self._audio_bytes // 32  # 16 kHz mono signed 16-bit PCM, bytes/ms

        def current(callback):
            def guarded(*args):
                if generation == self._audio_generation:
                    callback(*args)
            return guarded

        if self._dry_run:
            self._asr = DryRunAsr()
        elif self._live.uses_livetranslate:
            self._asr = LiveTranslate(
                self._shared.api_key, self._shared.websocket_url,
                target_language=self._live.target_language,
                phrases=self._guidance.static_phrases(),
                on_caption=current(lambda identifier,side,text,start,end,final,speaker:
                    self._accept_caption(f"lt-{generation}-{identifier}",side,text,
                                         start+offset,end+offset,final,speaker)),
                on_usage=current(self._accept_usage),
                on_error=current(self._on_asr_error),
            )
        else:
            self._asr = QwenStreamingAsr(
                self._shared.api_key, self._shared.websocket_url,
                source_language=self._live.source_language,
                on_partial=current(lambda text,start,end:self._emit_partial(text,start+offset,end+offset)),
                on_final=current(lambda text,start,end:self._accept_final(text,start+offset,end+offset)),
                on_error=current(self._on_asr_error),
            )
        self._asr.start()
        if not self._dry_run and not self._live.uses_livetranslate:
            # This streaming adapter does not expose authoritative audio usage yet.
            # Mark the estimate incomplete rather than silently omit its ASR cost.
            record_billing(self._shared.websocket_url, self._shared.api_key, self.model, None)
        if self._stop_requested.is_set():
            return
        self._capture = WasapiLoopbackCapture(
            self._live.audio_device, frame_ms=self._live.frame_ms,
            on_block=current(self._on_audio_block), on_error=current(self._on_capture_error),
        )
        self._paused.clear()
        self._capture.start()

    def request_pause(self, paused: bool) -> None:
        if self._stop_requested.is_set() or not self._started:
            return
        if paused:
            self._paused.set()  # Gate incoming frames immediately, before cleanup.
        threading.Thread(target=self._change_pause,args=(paused,),
                         name="yaki-live-pause",daemon=True).start()

    def _change_pause(self, paused: bool) -> None:
        with self._lifecycle_lock:
            if self._stop_requested.is_set() or not self._started:
                return
            try:
                if paused:
                    self._paused.set()
                    if self._capture is not None:
                        self._capture.stop()
                        self._capture = None
                    if self._asr is not None:
                        # Finish only pre-pause audio; queued translations may drain.
                        self._asr.stop()
                        self._asr = None
                    self._audio_generation += 1
                elif self._paused.is_set():
                    self._start_audio()
                if self._stop_requested.is_set():
                    return
                write_session_record(self._paths,self._live,self._provenance(),self.stats,
                                     status="paused" if paused else "running")
                self._bus.emit(ev.LiveEvent(
                    ev.KIND_SESSION_PAUSED if paused else ev.KIND_SESSION_RESUMED,
                    {"audio_position_ms":self._audio_bytes // 32},
                ))
            except Exception as error:
                self._bus.emit(ev.runtime_error(f"暂停/恢复失败：{error}"[:300]))
                self.stop("pause-resume-failed")

    def stop(self, reason: str = "stopped") -> dict:
        with self._lifecycle_lock:
            if self._stopped_event.is_set():
                return self.stats
            self._stop_requested.set()
            cleanup_errors: list[str] = []

            for component in (self._capture, self._asr):
                if component is None:
                    continue
                try:
                    component.stop()
                except Exception as error:
                    cleanup_errors.append(str(error))

            if self._recorder is not None:
                try:
                    self._recorder.stop()
                    self._set_stat("recorded_audio_bytes", self._recorder.bytes_written)
                    self._set_stat("recording_dropped", self._recorder.dropped_blocks)
                    if self._recorder.error:
                        cleanup_errors.append(f"录音写入失败：{self._recorder.error}")
                except Exception as error:
                    cleanup_errors.append(str(error))

            if self._translation_queue is not None:
                self._translation_queue.close(discard=True)
            if self._translator_thread is not None:
                self._translator_thread.join(timeout=10)
                if self._translator_thread.is_alive():
                    cleanup_errors.append("翻译请求仍在结束中，已停止接收其结果")

            try:
                with self._segments_lock:
                    segments = [dict(entry) for entry in self._segments]
                write_transcript(self._paths, segments)
                write_session_record(
                    self._paths,
                    self._live,
                    self._provenance(),
                    self.stats,
                    status="ended",
                    ended_reason=reason,
                )
            except Exception as error:
                cleanup_errors.append(f"会话落盘失败：{error}")

            for message in cleanup_errors:
                self._bus.emit(ev.runtime_error(message[:300]))
            stats = self.stats
            self._bus.emit(ev.session_ended(reason, stats))
            self._stopped_event.set()
            return stats

    def request_stop(self, reason: str = "stopped") -> None:
        if self._stop_requested.is_set() or self._stopped_event.is_set():
            return
        self._stop_requested.set()
        threading.Thread(
            target=self.stop,
            args=(reason,),
            name="yaki-live-stop",
            daemon=True,
        ).start()

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        return self._stopped_event.wait(timeout)

    @property
    def stopped(self) -> bool:
        return self._stopped_event.is_set()

    def _provenance(self) -> dict:
        return {
            "asr_model": "dry-run" if self._dry_run else self.model,
            "translation_model": (
                (self.model if self._live.uses_livetranslate else self._shared.translation_model)
                if self._live.translation_enabled else None
            ),
            "translation_engine": self._live.public()["translation_engine"],
            "asr_hints": list(languages.asr_hints(self._live.source_language)),
            "guidance": self._guidance.provenance if self._live.translation_enabled else [],
        }

    def _increment(self, name: str, amount: int = 1) -> None:
        with self._stats_lock:
            self._stats[name] += amount

    def _set_stat(self, name: str, value: int) -> None:
        with self._stats_lock:
            self._stats[name] = value

    # -- realtime chain ----------------------------------------------------

    def _accept_caption(self, segment_id, side, text, start_ms, end_ms, final, speaker_id):
        # Allow session.finish to drain the last captions while stop is pending,
        # but never modify a transcript after session_ended has been published.
        if self._stopped_event.is_set():
            return
        with self._segments_lock:
            entry = next((item for item in reversed(self._segments)
                          if item["segment_id"] == segment_id), None)
            if entry is None:
                entry = {"segment_id": segment_id, "source": "", "translation": "",
                         "start_ms": start_ms, "end_ms": end_ms, "final": False}
                self._segments.append(entry)
            already_final = entry["final"]
            entry.update({side: text, "end_ms": end_ms, "final": final, "speaker_id": speaker_id})
        if side == "translation":
            self._increment("translation_updates")
        if final and not already_final:
            self._increment("finals" if side == "source" else "translations")
        self._bus.emit(ev.caption_updated(segment_id,side,text,start_ms,end_ms,final,speaker_id))

    def _accept_usage(self, usage):
        record_billing(self._shared.websocket_url, self._shared.api_key, self.model, usage)
        def accumulate(target, values):
            for key, value in values.items():
                if key not in {"input_tokens", "output_tokens", "total_tokens", "audio_tokens",
                               "text_tokens", "input_tokens_details", "output_tokens_details"}:
                    continue
                if isinstance(value, dict):
                    accumulate(target.setdefault(key, {}), value)
                elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    target[key] = target.get(key, 0) + value
        with self._stats_lock:
            accumulate(self._usage, usage)
        self._bus.emit(ev.LiveEvent(ev.KIND_USAGE, {"model": self.model, "usage": usage}))

    def _on_audio_block(self, pcm: bytes) -> None:
        if self._stop_requested.is_set() or self._paused.is_set():
            return
        self._audio_bytes += len(pcm)
        self._increment("audio_blocks")
        if self._recorder is not None:
            if not self._recorder.write(pcm):
                self._increment("recording_dropped")
        try:
            if self._asr is not None:
                self._asr.send(pcm)
        except Exception as error:
            self._on_asr_error(f"发送音频帧失败：{error}")

    def _emit_partial(self, text: str, start_ms: int, end_ms: int) -> None:
        if self._stop_requested.is_set():
            return
        self._increment("partials")
        self._bus.emit(ev.partial_transcript(text, start_ms, end_ms))

    def _accept_final(self, text: str, start_ms: int, end_ms: int) -> None:
        if self._stop_requested.is_set():
            return
        with self._segments_lock:
            self._segment_seq += 1
            segment_id = f"live-{self._segment_seq:06d}"
            self._segments.append({
                "segment_id": segment_id, "start_ms": start_ms, "end_ms": end_ms,
                "source": text, "translation": "",
            })
        self._increment("finals")
        self._bus.emit(ev.final_transcript(segment_id, text, start_ms, end_ms))
        if self._translation_queue is not None:
            self._translation_queue.put(_FinalEntry(segment_id, start_ms, end_ms, text))

    def _on_translation_drop(self, entry: _FinalEntry) -> None:
        self._increment("translation_dropped")
        self._bus.emit(ev.translation_skipped(
            entry.segment_id, "翻译队列拥堵，按延迟优先策略丢弃最旧片段"
        ))
        self._mark_translation(entry.segment_id, "（因拥堵跳过）")

    def _translate_loop(self, translator: translation.DashScopeOpenAIClient) -> None:
        assert self._translation_queue is not None
        source = languages.NAMES.get(self._live.source_language, "Japanese")
        target = languages.NAMES.get(self._live.target_language, "Chinese")
        while True:
            if self._stop_requested.is_set():
                return
            entry = self._translation_queue.get(timeout=0.5)
            if entry is None:
                if self._stop_requested.is_set():
                    return
                continue
            try:
                terms = self._guidance.match(entry.text)
                if terms:
                    self._increment('guidance_terms',len(terms))
                    self._bus.emit(ev.notice('术语命中',segment_id=entry.segment_id,terms=terms))
                payload = translation.qwen_mt_payload(
                    entry.text, model=self._shared.translation_model,
                    source_language=source, target_language=target,
                    terms=terms,
                    domain_hint=self._guidance.domain_hint,
                )
                published = ""
                published_at = 0.0

                def publish_partial(text: str) -> None:
                    nonlocal published, published_at
                    if self._stop_requested.is_set():
                        raise RuntimeError("Live translation stopped")
                    if not text.strip() or text == published:
                        return
                    now = time.monotonic()
                    added = max(0, len(text) - len(published))
                    stable_boundary = text.endswith(("。", "！", "？", "，", "；", ".", "!", "?", ",", ";", "\n"))
                    corrected = bool(published) and not text.startswith(published)
                    if not corrected and added < 4 and not stable_boundary and now - published_at < 0.18:
                        return
                    published = text
                    published_at = now
                    self._increment("translation_updates")
                    self._bus.emit(ev.translation_partial(entry.segment_id, text))

                result = translator.chat_completions_stream(
                    payload, on_update=publish_partial, timeout_seconds=30
                )
            except Exception as error:
                if self._stop_requested.is_set():
                    return
                self._increment("translation_errors")
                self._bus.emit(ev.translation_error(entry.segment_id, str(error)[:300]))
                self._mark_translation(entry.segment_id, "（翻译失败）")
                continue
            if self._stop_requested.is_set():
                return
            if result.content != published:
                self._increment("translation_updates")
                self._bus.emit(ev.translation_partial(entry.segment_id, result.content))
            self._increment("translations")
            self._bus.emit(ev.translation(
                entry.segment_id, result.content, entry.text,
                result.model or self._shared.translation_model, result.elapsed_seconds,
            ))
            self._mark_translation(entry.segment_id, result.content)

    def _mark_translation(self, segment_id: str, text: str) -> None:
        with self._segments_lock:
            for entry in reversed(self._segments):
                if entry["segment_id"] == segment_id:
                    entry["translation"] = text
                    break

    # -- error paths ---------------------------------------------------------

    def _on_asr_error(self, message: str) -> None:
        self._bus.emit(ev.asr_error(message[:300]))
        self.request_stop("asr-error")

    def _on_capture_error(self, message: str) -> None:
        self._bus.emit(ev.capture_error(message[:300]))
        self.request_stop("capture-error")

    @property
    def stats(self) -> dict:
        with self._stats_lock:
            import copy
            return {**self._stats, **({"usage": copy.deepcopy(self._usage)} if self._usage else {})}
