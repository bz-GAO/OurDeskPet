"""Local ASR providers."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Iterable

from .providers import TimedSegment


class KotobaWhisperCppProvider:
    """Run a Kotoba GGML model through pywhispercpp.

    ``chunk_seconds`` is optional. A value around 15 seconds is slower but was
    materially more reliable for dense Japanese speech containing many numbers
    in the initial CPU smoke test. Native whisper.cpp VAD is intentionally not
    enabled here because the Python binding returned compressed-audio timestamps
    during the same test.
    """

    name = "kotoba_whisper_cpp"

    def __init__(
        self,
        model_path: Path,
        *,
        threads: int = 8,
        chunk_seconds: float | None = None,
        use_gpu: bool = False,
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(model_path)
        if chunk_seconds is not None and chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")
        if model_factory is None:
            from pywhispercpp.model import Model

            model_factory = Model
        self._chunk_seconds = chunk_seconds
        self._model = model_factory(
            str(model_path),
            context_params={"use_gpu": use_gpu},
            n_threads=threads,
            language="ja",
            translate=False,
            no_context=chunk_seconds is not None,
            print_progress=False,
            print_realtime=False,
            print_timestamps=False,
            suppress_non_speech_tokens=True,
            vad=False,
        )

    def transcribe(self, audio_path: Path, language: str = "ja") -> Iterable[TimedSegment]:
        if language != "ja":
            raise ValueError("KotobaWhisperCppProvider currently supports Japanese only")
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)

        if self._chunk_seconds is None:
            offset_segments = [(0, segment) for segment in self._model.transcribe(
                str(audio_path), extract_probability=True
            )]
        else:
            samples = self._model._load_audio(str(audio_path))
            chunk_size = int(self._chunk_seconds * 16_000)
            offset_segments = []
            for sample_offset in range(0, len(samples), chunk_size):
                chunk = samples[sample_offset : sample_offset + chunk_size]
                offset_ms = sample_offset * 1_000 // 16_000
                segments = self._model.transcribe(
                    chunk, extract_probability=True, no_context=True
                )
                offset_segments.extend((offset_ms, segment) for segment in segments)

        return [
            TimedSegment(
                segment_id=f"asr-{index:06}",
                start_ms=offset_ms + segment.t0 * 10,
                end_ms=offset_ms + segment.t1 * 10,
                text=segment.text.strip(),
                confidence=(
                    float(segment.probability)
                    if math.isfinite(float(segment.probability))
                    else None
                ),
            )
            for index, (offset_ms, segment) in enumerate(offset_segments, start=1)
        ]
