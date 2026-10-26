import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from scripts import full_video_pipeline as pipeline
from rinayaki.styling import (DEFAULT_FONT, FONT_FILES, GENSEN_FONT, PRESETS,
                              normalize_color, speaker_samples, validate_styles)
from rinayaki.style_preview import render_style_preview
from rinayaki.subtitles import SubtitleCue, SubtitleDocument, render_ass
from rinayaki.video_input import local_thumbnail
from rinayaki.settings import UserSettings


class WorkflowTests(unittest.TestCase):
    def test_style_preview_uses_bundled_fonts_and_outline(self):
        fonts = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
        default = render_style_preview('字幕预览', font_name=DEFAULT_FONT,
                                       fonts_directory=fonts, outline_color='#E55073')
        rounded = render_style_preview('字幕预览', font_name=GENSEN_FONT,
                                       fonts_directory=fonts, outline_color='#E55073')
        self.assertEqual(default.size, (720, 96))
        self.assertNotEqual(default.tobytes(), rounded.tobytes())
        self.assertEqual(set(FONT_FILES), {DEFAULT_FONT, GENSEN_FONT})

    def test_colors_and_per_speaker_ass(self):
        self.assertEqual(normalize_color('9ca5b9'),'#9CA5B9')
        with self.assertRaises(ValueError):
            normalize_color('red}')
        document = SubtitleDocument('ja','zh-Hans',(
            SubtitleCue('1',0,1000,'はい','是','0'),
            SubtitleCue('2',1000,2000,'いいえ','不','1')),
            metadata={'speaker_styles':{'0':{'color':PRESETS['璃奈'],'font':GENSEN_FONT}}})
        rendered = render_ass(document,mode='bilingual')
        self.assertIn(r'{\rSource}{\3c&H876D61&}',rendered)
        self.assertIn(r'{\rTranslation}{\3c&H876D61&\fnGenSenRounded2 JP}',rendered)
        self.assertIn(r'{\rSource}いいえ',rendered)
        self.assertEqual(validate_styles({'0':{'color':'#616D87','font':GENSEN_FONT}})['0']['font'],GENSEN_FONT)
        self.assertNotIn('#9CA5B9',PRESETS.values())

    def test_prepare_stops_before_subtitle_export_and_export_is_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            details = root/'intermediates'
            details.mkdir()
            source = details/'source.mp4'
            source.write_bytes(b'fixture')
            audio = details/'master.wav'
            audio.write_bytes(b'fixture')
            cues = [{'id':'1','start_ms':0,'end_ms':4000,'source_text':'はい','translation':'是','speaker_id':0},
                    {'id':'2','start_ms':5000,'end_ms':10000,'source_text':'いいえ','translation':'不','speaker_id':1}]
            args = argparse.Namespace(project_dir=root,url='https://example.com/video',input=None,yt_dlp=Path('unused'),ffmpeg=Path('unused'),stem='video',translation_batch_size=12,refinement_batch_size=20,phase='prepare')
            with patch.object(pipeline,'load_settings',return_value=UserSettings(api_key='unit-test-placeholder')), patch.object(pipeline,'prepare_source',return_value=(source,{'duration':10})), patch.object(pipeline,'extract_audio',return_value=audio), patch.object(pipeline,'transcribe',return_value={}), patch.object(pipeline,'translate',return_value=cues), patch.object(pipeline,'refine',return_value=cues), patch.object(pipeline,'export_and_mux') as export:
                self.assertEqual(pipeline.execute_job(args),0)
                export.assert_not_called()
            self.assertFalse((details/'subtitles').exists())
            prepared = json.loads((details/'prepared.json').read_text(encoding='utf-8'))
            self.assertEqual(set(prepared['speakers']),{'0','1'})
            self.assertEqual(json.loads((details/'progress.json').read_text())['status'],'awaiting_style')
            pipeline.write_json(details/'styles.json',{'prepared_key':prepared['key'],'speakers':{'0':{'color':'#9CA5B9'}}})
            args.phase = 'export'
            with patch.object(pipeline,'transcribe',side_effect=AssertionError('no ASR')), patch.object(pipeline,'translate',side_effect=AssertionError('no MT')), patch.object(pipeline,'export_and_mux',return_value={}) as export:
                self.assertEqual(pipeline.execute_job(args),0)
                self.assertEqual(export.call_args.kwargs['speaker_styles']['0']['color'],'#9CA5B9')

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_FFMPEG'),'local FFmpeg required')
    def test_local_thumbnail(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'视频 空格.mp4'
            ffmpeg = Path(os.environ['RINAYAKI_TEST_FFMPEG'])
            subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','color=c=red:s=320x180:d=1','-c:v','libx264',str(source)],check=True)
            root = ffmpeg.parents[2]
            data = local_thumbnail(str(source),1,root)
            image = Image.open(io.BytesIO(data))
            self.assertEqual(image.size,(640,360))
