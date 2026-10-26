"""WAV writer for the live audio stream.

Records the exact 16 kHz mono int16 stream the realtime ASR consumed, so a
finished session can later be promoted into an offline project for
higher-quality re-transcription without re-capturing anything.
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import wave


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2


class WaveRecorder:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=512)
        self._thread: threading.Thread | None = None
        self._written = 0
        self._dropped_blocks = 0
        self._error: str | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("录音器已经启动。")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="yaki-live-recorder", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            raise RuntimeError("录音文件打开超时。")
        if self._error:
            self._thread.join(timeout=1)
            self._thread = None
            raise RuntimeError(f"无法创建会话录音：{self._error}")

    def write(self, pcm: bytes) -> bool:
        if self._thread is None or not self._thread.is_alive() or not pcm:
            return False
        try:
            self._queue.put_nowait(pcm)
            return True
        except queue.Full:
            self._dropped_blocks += 1
            return False  # recording must never slow the realtime chain

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        while True:
            try:
                self._queue.put_nowait(None)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._dropped_blocks += 1
                except queue.Empty:
                    continue
        thread.join(timeout=10)
        if not thread.is_alive():
            self._thread = None

    def _run(self) -> None:
        try:
            with wave.open(str(self._path), "wb") as handle:
                handle.setnchannels(CHANNELS)
                handle.setsampwidth(SAMPLE_WIDTH)
                handle.setframerate(SAMPLE_RATE)
                self._ready.set()
                while True:
                    block = self._queue.get()
                    if block is None:
                        break
                    handle.writeframes(block)
                    self._written += len(block) // SAMPLE_WIDTH
        except Exception as error:
            self._error = str(error)
        finally:
            self._ready.set()

    @property
    def bytes_written(self) -> int:
        return self._written * SAMPLE_WIDTH

    @property
    def dropped_blocks(self) -> int:
        return self._dropped_blocks

    @property
    def error(self) -> str | None:
        return self._error
