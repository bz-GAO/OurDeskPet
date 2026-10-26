import base64
import tempfile
import unittest
from pathlib import Path

from rinayaki.cloud_asr import (
    FILETRANS_MODEL,
    SHORT_FILE_MODEL,
    audio_data_uri,
    filetrans_payload,
    short_file_payload,
)


class CloudAsrPayloadTests(unittest.TestCase):
    def test_short_file_payload_has_exact_model_and_language(self) -> None:
        payload = short_file_payload(
            "data:audio/wav;base64,AAAA", audio_format="wav", vocabulary={"璃奈": 5}
        )
        self.assertEqual(payload["model"], SHORT_FILE_MODEL)
        self.assertEqual(payload["parameters"]["language_hints"], ["ja"])
        self.assertEqual(payload["parameters"]["vocabulary"], {"璃奈": 5})
        self.assertEqual(
            payload["input"]["messages"][0]["content"][0]["type"], "input_audio"
        )

    def test_filetrans_enables_diarization_without_guessing_speaker_count(self) -> None:
        payload = filetrans_payload("https://example.com/audio.wav")
        self.assertEqual(payload["model"], FILETRANS_MODEL)
        self.assertTrue(payload["parameters"]["diarization_enabled"])
        self.assertNotIn("speaker_count", payload["parameters"])
        self.assertEqual(payload["parameters"]["channel_id"], [0])

    def test_filetrans_accepts_configured_compatible_model(self) -> None:
        payload = filetrans_payload("https://example.com/audio.wav", model="custom-filetrans")
        self.assertEqual(payload["model"], "custom-filetrans")

    def test_filetrans_rejects_local_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTP.*oss"):
            filetrans_payload("E:/audio.wav")

    def test_filetrans_accepts_dashscope_temporary_oss_url(self) -> None:
        payload = filetrans_payload("oss://dashscope-instant/example/audio.wav")
        self.assertEqual(
            payload["input"]["file_urls"],
            ["oss://dashscope-instant/example/audio.wav"],
        )

    def test_audio_data_uri_is_base64(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.wav"
            path.write_bytes(b"RIFFtest")
            format_name, uri = audio_data_uri(path)
        self.assertEqual(format_name, "wav")
        self.assertEqual(uri, "data:audio/wav;base64," + base64.b64encode(b"RIFFtest").decode())


if __name__ == "__main__":
    unittest.main()
