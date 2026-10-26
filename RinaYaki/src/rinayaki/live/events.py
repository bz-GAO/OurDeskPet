"""Typed event stream for live sessions.

Every observable step of the realtime chain is expressed as a ``LiveEvent``
so sinks (subtitle window, console), the JSONL session log and a future
offline handoff all consume the same stream. Events are immutable snapshots;
no event carries credentials.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import threading
import time
from typing import Any


KIND_SESSION_STARTED = "session_started"
KIND_SESSION_ENDED = "session_ended"
KIND_SESSION_PAUSED = "session_paused"
KIND_SESSION_RESUMED = "session_resumed"
KIND_PARTIAL_TRANSCRIPT = "partial_transcript"
KIND_FINAL_TRANSCRIPT = "final_transcript"
KIND_TRANSLATION_PARTIAL = "translation_partial"
KIND_TRANSLATION = "translation"
KIND_TRANSLATION_SKIPPED = "translation_skipped"
KIND_TRANSLATION_ERROR = "translation_error"
KIND_ASR_ERROR = "asr_error"
KIND_CAPTURE_ERROR = "capture_error"
KIND_RUNTIME_ERROR = "runtime_error"
KIND_NOTICE = "notice"
KIND_CAPTION_UPDATED = "caption_updated"
KIND_USAGE = "usage"


def caption_updated(segment_id: str, side: str, text: str, start_ms: int,
                    end_ms: int, final: bool, speaker_id=None) -> LiveEvent:
    return LiveEvent(KIND_CAPTION_UPDATED, {
        "segment_id": segment_id, "side": side, "text": text,
        "start_ms": start_ms, "end_ms": end_ms, "final": final,
        "speaker_id": speaker_id,
    })


@dataclass(frozen=True, slots=True)
class LiveEvent:
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return {"ts": self.timestamp, "kind": self.kind, **dict(self.payload)}


def session_started(session_dir: str, config: Mapping[str, Any]) -> LiveEvent:
    return LiveEvent(KIND_SESSION_STARTED, {"session_dir": session_dir, "config": dict(config)})


def session_ended(reason: str, stats: Mapping[str, Any]) -> LiveEvent:
    return LiveEvent(KIND_SESSION_ENDED, {"reason": reason, "stats": dict(stats)})


def partial_transcript(text: str, start_ms: int, end_ms: int) -> LiveEvent:
    return LiveEvent(KIND_PARTIAL_TRANSCRIPT, {"text": text, "start_ms": start_ms, "end_ms": end_ms})


def final_transcript(segment_id: str, text: str, start_ms: int, end_ms: int) -> LiveEvent:
    return LiveEvent(KIND_FINAL_TRANSCRIPT, {
        "segment_id": segment_id, "text": text, "start_ms": start_ms, "end_ms": end_ms,
    })


def translation(segment_id: str, text: str, source_text: str, model: str, elapsed_seconds: float) -> LiveEvent:
    return LiveEvent(KIND_TRANSLATION, {
        "segment_id": segment_id, "text": text, "source_text": source_text,
        "model": model, "elapsed_seconds": round(elapsed_seconds, 3),
    })


def translation_partial(segment_id: str, text: str) -> LiveEvent:
    return LiveEvent(KIND_TRANSLATION_PARTIAL, {"segment_id": segment_id, "text": text})


def translation_skipped(segment_id: str, reason: str) -> LiveEvent:
    return LiveEvent(KIND_TRANSLATION_SKIPPED, {"segment_id": segment_id, "reason": reason})


def translation_error(segment_id: str, message: str) -> LiveEvent:
    return LiveEvent(KIND_TRANSLATION_ERROR, {"segment_id": segment_id, "message": message})


def asr_error(message: str) -> LiveEvent:
    return LiveEvent(KIND_ASR_ERROR, {"message": message})


def capture_error(message: str) -> LiveEvent:
    return LiveEvent(KIND_CAPTURE_ERROR, {"message": message})


def runtime_error(message: str) -> LiveEvent:
    return LiveEvent(KIND_RUNTIME_ERROR, {"message": message})


def notice(message: str, **extra: Any) -> LiveEvent:
    return LiveEvent(KIND_NOTICE, {"message": message, **extra})


class EventBus:
    """Fan-out to in-process subscribers. Subscriber errors never propagate."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[LiveEvent], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[LiveEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def emit(self, event: LiveEvent) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # sinks must not break the realtime chain
                pass


class EventLog:
    """Append-only JSONL persistence; install as an EventBus subscriber."""

    def __init__(self, path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._file = None

    def handle(self, event: LiveEvent) -> None:
        import json

        line = json.dumps(event.to_json(), ensure_ascii=False) + "\n"
        with self._lock:
            if self._file is None:
                self._file = open(self._path, "a", encoding="utf-8", buffering=1)
            self._file.write(line)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
