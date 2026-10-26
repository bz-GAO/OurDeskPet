import unittest
import tempfile
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock
from rinayaki.translation import ApiResult

from scripts.full_video_pipeline import parse_numbered_translation, parse_refinement_json, cached_response, ffmpeg_filter_path


class FullVideoPipelineTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_FFMPEG'), 'opt-in local FFmpeg integration')
    def test_subtitle_filter_preserves_special_characters_in_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="Yaki's [paths], ") as directory:
            root = Path(directory)
            captions = root / "captions';[1],.srt"
            captions.write_text('1\n00:00:00,000 --> 00:00:01,000\nTest\n', encoding='utf-8')
            font_dir = root / "fonts';[1],"
            font_dir.mkdir()
            result = subprocess.run([
                os.environ['RINAYAKI_TEST_FFMPEG'], '-hide_banner', '-v', 'error',
                '-f', 'lavfi', '-i', 'color=c=black:s=32x32:d=0.1',
                '-vf', f'subtitles=filename={ffmpeg_filter_path(captions)}:fontsdir={ffmpeg_filter_path(font_dir)}',
                '-frames:v', '1', '-f', 'null', '-',
            ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_resume_reuses_only_matching_requests(self) -> None:
        client = Mock()
        client.chat_completions.return_value = ApiResult("test", "[0001] hello", 1.0, {}, "id", "stop")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            cached_response(client, {"input": "a"}, path, ["0001"], 1)
            cached_response(client, {"input": "a"}, path, ["0001"], 1)
            self.assertEqual(client.chat_completions.call_count, 1)
            cached_response(client, {"input": "b"}, path, ["0001"], 1)
            self.assertEqual(client.chat_completions.call_count, 2)

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_numbered_translation("[0001] a\n[0001] b", ["0001"])
        with self.assertRaises(ValueError):
            parse_refinement_json('[{"id":"0001","translation":"a"},{"id":"0001","translation":"b"}]', ["0001"])

    def test_parses_numbered_translation(self) -> None:
        result = parse_numbered_translation("[0001] 你好\n[0002] 再见", ["0001", "0002"])
        self.assertEqual(result, {"0001": "你好", "0002": "再见"})

    def test_parses_fenced_refinement_json(self) -> None:
        result = parse_refinement_json(
            '```json\n[{"id":"0001","translation":"你好"}]\n```', ["0001"]
        )
        self.assertEqual(result, {"0001": "你好"})

    def test_rejects_missing_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "0002"):
            parse_numbered_translation("[0001] 你好", ["0001", "0002"])


if __name__ == "__main__":
    unittest.main()
