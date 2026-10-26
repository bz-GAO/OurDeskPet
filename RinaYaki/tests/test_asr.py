import math
import tempfile
import unittest
from pathlib import Path

from rinayaki.asr import KotobaWhisperCppProvider


class FakeSegment:
    def __init__(self, t0: int, t1: int, text: str, probability: float) -> None:
        self.t0 = t0
        self.t1 = t1
        self.text = text
        self.probability = probability


class FakeModel:
    def __init__(self, _model_path: str, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls = 0

    def _load_audio(self, _path: str) -> list[float]:
        return [0.0] * 32_000

    def transcribe(self, _audio: object, **_kwargs: object) -> list[FakeSegment]:
        self.calls += 1
        return [FakeSegment(0, 50, f" chunk {self.calls} ", math.nan)]


class KotobaProviderTests(unittest.TestCase):
    def test_chunk_offsets_preserve_source_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.bin"
            audio = root / "audio.wav"
            model.touch()
            audio.touch()
            created: list[FakeModel] = []

            def factory(path: str, **kwargs: object) -> FakeModel:
                instance = FakeModel(path, **kwargs)
                created.append(instance)
                return instance

            provider = KotobaWhisperCppProvider(
                model, chunk_seconds=1, model_factory=factory
            )
            segments = list(provider.transcribe(audio))

            self.assertEqual([segment.start_ms for segment in segments], [0, 1000])
            self.assertEqual([segment.end_ms for segment in segments], [500, 1500])
            self.assertEqual([segment.text for segment in segments], ["chunk 1", "chunk 2"])
            self.assertTrue(all(segment.confidence is None for segment in segments))
            self.assertFalse(created[0].kwargs["vad"])

    def test_rejects_non_japanese_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.bin"
            audio = root / "audio.wav"
            model.touch()
            audio.touch()
            provider = KotobaWhisperCppProvider(model, model_factory=FakeModel)
            with self.assertRaises(ValueError):
                list(provider.transcribe(audio, language="en"))


if __name__ == "__main__":
    unittest.main()
