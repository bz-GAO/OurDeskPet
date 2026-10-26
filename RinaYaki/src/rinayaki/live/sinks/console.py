"""Headless console sink; prints status and final translations."""
from __future__ import annotations

import sys

from .. import events as ev


class ConsoleSink:
    def __init__(self, stream=None, display_mode: str = "bilingual") -> None:
        self._stream = stream or sys.stdout
        self._display_mode = display_mode

    def handle(self, event: ev.LiveEvent) -> None:
        if event.kind == ev.KIND_CAPTION_UPDATED and event.payload["final"]:
            side = event.payload["side"]
            if self._display_mode == "bilingual" or self._display_mode == side:
                print(event.payload["text"], file=self._stream, flush=True)
        elif event.kind == ev.KIND_TRANSLATION and self._display_mode != "source":
            print(f"  {event.payload['text']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_FINAL_TRANSCRIPT and self._display_mode != "translation":
            print(event.payload["text"], file=self._stream, flush=True)
        elif event.kind == ev.KIND_ASR_ERROR:
            print(f"[ASR] {event.payload['message']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_CAPTURE_ERROR:
            print(f"[采集] {event.payload['message']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_RUNTIME_ERROR:
            print(f"[运行] {event.payload['message']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_TRANSLATION_ERROR:
            print(f"[翻译] {event.payload['message']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_TRANSLATION_SKIPPED:
            print(f"[翻译跳过] {event.payload['reason']}", file=self._stream, flush=True)
        elif event.kind == ev.KIND_SESSION_ENDED:
            print(f"[会话结束] {event.payload['stats']}", file=self._stream, flush=True)
