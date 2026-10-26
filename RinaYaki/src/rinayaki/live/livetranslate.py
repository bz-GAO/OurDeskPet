"""Text-only Qwen3.8 live translation, isolated from ASR + MT.

Input and output items are independent streams: the documented protocol does
not promise identical segmentation or expose a universal input/output pairing.
Never guess a correspondence by FIFO or by the currently active speaker.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
from collections.abc import Callable
import json
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MODEL = "qwen3.8-livetranslate-flash-realtime"


def realtime_url(asr_url: str) -> str:
    """Use the configured provider/region; never send its key to a fallback host."""
    parts = urlsplit(asr_url)
    if parts.scheme != "wss" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("实时语音地址无效。")
    path = parts.path.rstrip("/")
    if path.endswith("/inference"):
        path = path[:-len("inference")] + "realtime"
    elif not path.endswith("/realtime"):
        raise ValueError("LiveTranslate 需要 inference 或 realtime 接口地址。")
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "model"]
    query.append(("model", MODEL))
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def session_update(target_language: str, phrases: dict[str, str] | None = None) -> dict:
    target = {"zh-Hans": "zh", "en": "en", "ja": "ja"}.get(target_language)
    if target is None:
        raise ValueError("LiveTranslate 不支持此目标语言。")
    # Even text-only sessions can validate a server-default voice on first
    # speech. Override it explicitly, without enabling any audio generation.
    translation = {"language": target}
    if phrases:
        translation["corpus"] = {"phrases": phrases}
    return {"type": "session.update", "session": {
        "output_modalities": ["text"],
        "audio": {"input": {
            "format": {"type": "pcm", "sample_rate": 16000},
            "turn_detection": {"type": "speaker_detection", "threshold": 0.5},
        }, "output": {"voice": "Tina"}},
        "translation": translation,
    }}


class LiveTranslate:
    def __init__(self, api_key: str, websocket_url: str, *, target_language: str,
                 on_caption: Callable, on_usage: Callable, on_error: Callable,
                 connect=None, finish_timeout: float = 8,
                 phrases: dict[str, str] | None = None) -> None:
        self._key = api_key
        self._url = realtime_url(websocket_url)
        self._config = session_update(target_language, phrases)
        self._on_caption = on_caption
        self._on_usage = on_usage
        self._on_error = on_error
        self._connect = connect
        self._finish_timeout = finish_timeout
        self._socket = None
        self._thread = None
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        self._finishing = threading.Event()
        self._finished = threading.Event()
        self._terminal = threading.Event()
        self._failed = threading.Event()
        self._audio_ms = 0
        self._audio_bytes = 0
        self._items: OrderedDict[str, dict] = OrderedDict()
        self._seen: OrderedDict[str, None] = OrderedDict()

    def _message(self, payload: dict) -> None:
        with self._send_lock:
            if self._socket is not None:
                self._socket.send(json.dumps(payload, ensure_ascii=False))

    def start(self) -> None:
        import websocket
        connect = self._connect or websocket.create_connection
        if not self._key:
            raise ValueError("未配置 API Key。")
        try:
            self._socket = connect(self._url, header=["Authorization: Bearer " + self._key],
                                   timeout=10, enable_multithread=True)
            self._message(self._config)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                event = json.loads(self._socket.recv())
                if event.get("type") == "error":
                    raise RuntimeError("LiveTranslate 配置失败，请检查模型权限和接口地址。")
                if event.get("type") == "session.updated":
                    if event.get("session", {}).get("output_modalities") != ["text"]:
                        raise RuntimeError("LiveTranslate 未确认纯字幕模式，已停止。")
                    self._socket.settimeout(1)
                    self._thread = threading.Thread(target=self._receive, name="yaki-livetranslate", daemon=True)
                    self._thread.start()
                    return
            raise RuntimeError("LiveTranslate 连接超时。")
        except Exception:
            self._close()
            # Do not surface WebSocket exceptions: headers/keys can be embedded.
            raise RuntimeError("LiveTranslate 连接失败，请检查网络、接口地址和模型权限。") from None

    def send(self, pcm_block: bytes) -> None:
        if self._closed.is_set() or self._finishing.is_set():
            return
        if self._failed.is_set():
            raise RuntimeError("LiveTranslate 连接已断开。")
        self._audio_bytes += len(pcm_block)
        self._audio_ms = self._audio_bytes // 32
        try:
            self._message({"type": "input_audio_buffer.append",
                           "audio": base64.b64encode(pcm_block).decode("ascii")})
        except Exception:
            raise RuntimeError("LiveTranslate 音频发送失败。") from None

    def _receive(self) -> None:
        import websocket
        try:
            while not self._closed.is_set():
                try:
                    raw = self._socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    if not self._finished.is_set():
                        self._fail("LiveTranslate 连接已断开。")
                    return
                self.handle_event(json.loads(raw))
                if self._finished.is_set() or self._failed.is_set():
                    return
        except Exception:
            if not self._closed.is_set():
                self._fail("LiveTranslate 接收失败。")

    def _fail(self, message: str) -> None:
        if not self._failed.is_set():
            self._failed.set()
            self._terminal.set()
            self._on_error(message)

    def _item(self, identifier: str) -> dict:
        if identifier not in self._items:
            self._items[identifier] = {
                "text": "", "start_ms": self._audio_ms, "end_ms": self._audio_ms,
                "final": False, "speaker_id": None,
            }
            # Keep only a bounded window of finished items. Never discard a
            # currently streaming item to make space for a later response.
            if len(self._items) > 256:
                for key, item in list(self._items.items()):
                    if item["final"]:
                        del self._items[key]
                        if len(self._items) <= 192:
                            break
            if len(self._items) > 256:
                raise RuntimeError("LiveTranslate 未完成片段过多。")
        return self._items[identifier]

    def handle_event(self, event: dict) -> None:
        """Protocol normalization; also usable with prerecorded event fixtures."""
        event_id = event.get("event_id")
        if event_id:
            if event_id in self._seen:
                return
            self._seen[event_id] = None
            if len(self._seen) > 1024:
                self._seen.popitem(last=False)
        kind = event.get("type")
        if kind == "session.finished":
            self._finished.set()
            self._terminal.set()
        elif kind in {"error", "conversation.item.input_audio_transcription.failed"}:
            self._fail("LiveTranslate 处理失败，请检查模型权限或稍后重试。")
        elif kind in {"input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"}:
            identifier = event.get("item_id")
            if identifier:
                item = self._item("source-" + identifier)
                field = "start_ms" if kind.endswith("started") else "end_ms"
                item[field] = int(event.get("audio_start_ms" if field == "start_ms" else "audio_end_ms") or 0)
                item["speaker_id"] = event.get("speaker_id", item["speaker_id"])
        elif kind in {"conversation.item.input_audio_transcription.delta",
                      "conversation.item.input_audio_transcription.completed",
                      "response.text.delta", "response.text.done"}:
            source = kind.startswith("conversation.")
            identifier = event.get("item_id")
            if not identifier:
                return
            side = "source" if source else "translation"
            identifier = side + "-" + identifier
            item = self._item(identifier)
            if item["final"]:
                return
            final = kind.endswith(("completed", "done"))
            item["text"] = (str(event.get("transcript" if source else "text", item["text"]))
                            if final else item["text"] + str(event.get("delta") or ""))
            item["final"] = final
            item["end_ms"] = max(item["end_ms"], self._audio_ms)
            if item["text"]:
                self._on_caption(identifier, side, item["text"], item["start_ms"],
                                 item["end_ms"], final, item["speaker_id"])
        elif kind == "response.done":
            response = event.get("response") or {}
            usage = response.get("usage") or {}
            if usage:
                self._on_usage(usage)
            if response.get("status") in {"failed", "incomplete", "cancelled"}:
                self._fail("LiveTranslate 翻译未完成。")
            # Some transports omit text.done; keep the response's final text.
            for output in response.get("output") or []:
                for part in output.get("content") or []:
                    if part.get("type") == "text" and output.get("id"):
                        self.handle_event({"type": "response.text.done", "item_id": output["id"],
                                           "text": part.get("text") or ""})

    def stop(self) -> None:
        if self._socket is None:
            return
        self._finishing.set()
        timed_out = False
        try:
            if not self._failed.is_set():
                self._message({"type": "session.finish"})
                timed_out = not self._terminal.wait(self._finish_timeout)
        except Exception:
            timed_out = True
        finally:
            self._close()
        if timed_out:
            raise RuntimeError("LiveTranslate 结束超时，已关闭连接并保留收到的字幕。")

    def _close(self) -> None:
        self._closed.set()
        socket, self._socket = self._socket, None
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
