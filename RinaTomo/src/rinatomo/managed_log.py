"""Bounded capture of an owned child process's stdout and stderr."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import BinaryIO

log = logging.getLogger(__name__)

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 2
READ_CHUNK_BYTES = 8192


class ManagedProcessLog:
    """Drain raw output in fixed chunks into a bounded set of local log files."""

    def __init__(
        self, path: Path, *, max_bytes: int = LOG_MAX_BYTES, backups: int = LOG_BACKUPS
    ) -> None:
        if max_bytes < 1 or backups < 1:
            raise ValueError("log limits must be positive")
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._stream: BinaryIO | None = None
        self._thread: threading.Thread | None = None
        self._file: BinaryIO | None = None
        path.parent.mkdir(parents=True, exist_ok=True)
        # Adopt older unbounded logs by keeping their last max_bytes bytes.
        candidates = (path, *(self._backup(i) for i in range(1, backups + 1)))
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size > max_bytes:
                with candidate.open("r+b") as output:
                    output.seek(-max_bytes, 2)
                    tail = output.read(max_bytes)
                    output.seek(0)
                    output.write(tail)
                    output.truncate()
        self._file = path.open("ab", buffering=0)
        self._size = self._file.tell()

    def _backup(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def _rotate(self) -> None:
        assert self._file is not None
        self._file.close()
        self._file = None
        for index in range(self.backups - 1, 0, -1):
            previous = self._backup(index)
            if previous.exists():
                previous.replace(self._backup(index + 1))
        self.path.replace(self._backup(1))
        self._file = self.path.open("wb", buffering=0)
        self._size = 0

    def _write(self, data: bytes) -> None:
        with self._lock:
            if self._file is None:
                return
            remaining = memoryview(data)
            while remaining:
                if self._size >= self.max_bytes:
                    self._rotate()
                amount = min(len(remaining), self.max_bytes - self._size)
                assert self._file is not None
                written = self._file.write(remaining[:amount])
                if not written:
                    raise OSError("managed process log write made no progress")
                self._size += written
                remaining = remaining[written:]

    def start(self, stream: BinaryIO | None) -> None:
        if stream is None:
            raise ValueError("managed process log needs a piped output stream")
        self._stream = stream
        self._thread = threading.Thread(
            target=self._drain, name="RinaTomoNapCatLog", daemon=True
        )
        self._thread.start()

    def _drain(self) -> None:
        stream = self._stream
        assert stream is not None
        write_failed = False
        try:
            while not self._stop.is_set():
                data = stream.read(READ_CHUNK_BYTES)
                if not data:
                    break
                if not write_failed:
                    try:
                        self._write(data)
                    except OSError:
                        # A full disk must not leave QQ blocked on its output.
                        write_failed = True
                        log.exception("could not write managed NapCat log")
        except (OSError, ValueError):
            if not self._stop.is_set():
                log.exception("could not read managed NapCat output")
        finally:
            try:
                stream.close()
            finally:
                self._close_file()

    def _close_file(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    def close(self) -> None:
        """After the child stops, allow EOF to flush before cancelling the reader."""
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._stop.set()
        if self._stream is not None:
            self._stream.close()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if thread.is_alive():
                log.error("managed NapCat log reader did not stop after its pipe closed")
        self._close_file()
