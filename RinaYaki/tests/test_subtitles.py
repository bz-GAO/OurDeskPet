import json
import tempfile
import unittest
from pathlib import Path

from rinayaki.subtitles import (
    SubtitleCue,
    SubtitleDocument,
    export_subtitles,
    load_subtitle_document,
    render_ass,
    render_srt,
    render_vtt,
    _wrap_screen_text,
    _subtitle_font,
)


class SubtitleExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = SubtitleDocument(
            source_language="ja",
            target_language="zh-Hans",
            cues=(
                SubtitleCue("s1", 1_234, 4_567, "こんにちは。", "你好。", "speaker-1"),
                SubtitleCue("s2", 65_000, 67_010, "またね。", "回头见。"),
            ),
        )

    def test_srt_and_vtt_timestamps(self) -> None:
        srt = render_srt(self.document, mode="translated")
        vtt = render_vtt(self.document, mode="source")
        self.assertIn("00:00:01,234 --> 00:00:04,567", srt)
        self.assertIn("00:01:05.000 --> 00:01:07.010", vtt)
        self.assertTrue(vtt.startswith("WEBVTT\n"))

    def test_ass_contains_styles_speaker_and_bilingual_text(self) -> None:
        ass = render_ass(self.document, mode="bilingual")
        self.assertIn("Style: Translation,Noto Sans CJK SC Medium,68,&H00FFFFFF", ass)
        self.assertIn("Style: Source,Noto Sans CJK JP Medium,48,&H00FFFFFF", ass)
        self.assertIn("0:00:01.23,0:00:04.56,Translation,speaker-1", ass)
        self.assertIn(r"{\rSource}こんにちは。\N{\rTranslation}你好。", ass)

    def test_translated_export_rejects_missing_translation(self) -> None:
        document = SubtitleDocument(
            source_language="ja",
            target_language="zh-Hans",
            cues=(SubtitleCue("s1", 0, 1000, "原文"),),
        )
        with self.assertRaisesRegex(ValueError, "has no translation"):
            render_srt(document, mode="translated")

    def test_long_bilingual_cues_wrap_within_two_thirds_of_screen(self) -> None:
        source = '日本各地の様々な魅力を探し発信していく、田中千恵美の田中の彼方、第69回がスタートいたします。' * 2
        translated = '通过探索日本各地的魅力，田中千惠美的田中的彼方第六十九期现在开始。' * 3
        wrapped_source = _wrap_screen_text(source, region='jp', size=48)
        wrapped_target = _wrap_screen_text(translated, region='sc', size=68)
        for line in wrapped_source.splitlines():
            self.assertLessEqual(_subtitle_font('jp', 48).getlength(line), 1280)
        for line in wrapped_target.splitlines():
            self.assertLessEqual(_subtitle_font('sc', 68).getlength(line), 1280)
        document = SubtitleDocument('ja', 'zh-Hans', (SubtitleCue('long', 0, 10000, source, translated),))
        ass = render_ass(document, mode='bilingual')
        self.assertGreater(ass.count(r'\N'), 1)
        self.assertEqual(ass.count('Dialogue:'), 1)

    def test_gensen_uses_its_own_metrics(self) -> None:
        text = '圆润字幕字体测试。' * 20
        wrapped = _wrap_screen_text(text,region='sc',size=68,font_name='GenSenRounded2 JP')
        for line in wrapped.splitlines():
            self.assertLessEqual(_subtitle_font('sc',68,'GenSenRounded2 JP').getlength(line),1280)

    def test_loads_asr_json_and_exports_canonical_json(self) -> None:
        payload = {
            "language": "ja",
            "model": "kotoba-test",
            "segments": [
                {"id": "s1", "start_ms": 0, "end_ms": 1000, "text": "原文", "confidence": 0.8}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.json"
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            document = load_subtitle_document(source)
            written = export_subtitles(document, root / "out", stem="demo", formats=("json", "srt"))
            self.assertEqual(len(written), 2)
            canonical = json.loads((root / "out" / "demo.subtitles.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical["cues"][0]["confidence"], 0.8)
            self.assertIsNone(canonical["cues"][0]["speaker_id"])


if __name__ == "__main__":
    unittest.main()
