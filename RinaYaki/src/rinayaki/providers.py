"""Stable provider boundaries for future local and remote implementations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class TimedSegment:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str
    speaker_id: str | None = None
    confidence: float | None = None


class AcquisitionProvider(Protocol):
    name: str

    def probe(self, source: str) -> Mapping[str, object]: ...

    def acquire(self, source: str, destination: Path) -> Mapping[str, object]: ...


class AsrProvider(Protocol):
    name: str

    def transcribe(self, audio_path: Path, language: str = "ja") -> Iterable[TimedSegment]: ...


class TranslationProvider(Protocol):
    name: str

    def translate(
        self,
        segments: Iterable[TimedSegment],
        *,
        source_language: str = "ja",
        target_language: str = "zh",
    ) -> Mapping[str, str]: ...


class LiveAsrProvider(Protocol):
    """Streaming providers may revise previously emitted partial hypotheses."""

    name: str

    def push_audio(self, pcm: bytes, timestamp_ms: int) -> Iterable[TimedSegment]: ...

    def finish(self) -> Iterable[TimedSegment]: ...
