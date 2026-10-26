import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from rinayaki.job import job_lock, read_cached
from rinayaki.translation import ApiResult
from scripts import full_video_pipeline as pipeline


class JobTests(unittest.TestCase):
    def test_lock_blocks_concurrent_writer_and_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                with job_lock(root):
                    with self.assertRaises(RuntimeError):
                        with job_lock(root):
                            pass
                    raise ValueError('fixture failure')
            with job_lock(root):
                pass

    def test_corrupt_stage_cache_is_a_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'cache.json'
            p.write_text('{')
            self.assertIsNone(read_cached(p, 'key'))

    def test_translation_cache_tracks_asr_and_parameters(self):
        client = Mock()
        client.chat_completions.return_value = ApiResult('test', '[0001] hello', 0, {}, 'id', 'stop')
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline.DashScopeOpenAIClient, 'from_environment', return_value=client):
            root = Path(directory)
            source = {'sentences': [{'begin_time': 0, 'end_time': 1000, 'text': 'first'}]}
            pipeline.translate(source, root, project_root=root, batch_size=12)
            pipeline.translate(source, root, project_root=root, batch_size=12)
            self.assertEqual(client.chat_completions.call_count, 1)
            source['sentences'][0]['text'] = 'changed'
            result = pipeline.translate(source, root, project_root=root, batch_size=12)
            self.assertEqual(client.chat_completions.call_count, 2)
            self.assertEqual(result[0]['source_text'], 'changed')

    def test_refinement_cache_tracks_changed_draft(self):
        client = Mock()
        client.chat_completions.return_value = ApiResult('test', '[{"id":"0001","translation":"final"}]', 0, {}, 'id', 'stop')
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline.DashScopeOpenAIClient, 'from_environment', return_value=client):
            root = Path(directory)
            cues = [{'id':'0001', 'source_text':'original', 'draft_translation':'first'}]
            pipeline.refine(cues, root, project_root=root, batch_size=20)
            pipeline.refine(cues, root, project_root=root, batch_size=20)
            self.assertEqual(client.chat_completions.call_count, 1)
            cues[0]['draft_translation'] = 'changed'
            pipeline.refine(cues, root, project_root=root, batch_size=20)
            self.assertEqual(client.chat_completions.call_count, 2)

    def test_missing_numbered_cues_recover_individually_and_resume(self):
        client = Mock()
        client.chat_completions.side_effect = [ApiResult('test', '[0001] merged', 0, {}, 'id', 'stop'),
            ApiResult('test', 'one', 0, {}, 'id', 'stop'), ApiResult('test', 'two', 0, {}, 'id', 'stop')]
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline.DashScopeOpenAIClient, 'from_environment', return_value=client):
            root = Path(directory)
            source = {'sentences':[{'begin_time':0,'end_time':1000,'text':'first'}, {'begin_time':1000,'end_time':2000,'text':'second'}]}
            result = pipeline.translate(source, root, project_root=root, batch_size=12)
            self.assertEqual([c['draft_translation'] for c in result], ['one', 'two'])
            pipeline.translate(source, root, project_root=root, batch_size=12)
            self.assertEqual(client.chat_completions.call_count, 3)
            batch = json.loads((root/'work/04_translation/batches/001.json').read_text())
            self.assertEqual(batch['recovery']['strategy'], 'single-cue')

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_FFMPEG'), 'opt-in local FFmpeg integration')
    def test_cold_pipeline_recovers_without_operator_then_resumes_offline(self):
        @dataclass
        class AsrFixture:
            sentences: list
        ffmpeg = Path(os.environ['RINAYAKI_TEST_FFMPEG'])
        with tempfile.TemporaryDirectory(prefix='Yaki automated ') as directory:
            root = Path(directory)
            source = root / 'fixture.mp4'
            subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=640x360:d=2', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(source)], check=True)
            output = root / 'job'
            args = argparse.Namespace(url=None, input=source, project_dir=output, stem='fixture',
                yt_dlp=Path('unused'), ffmpeg=ffmpeg, translation_batch_size=12, refinement_batch_size=20)
            asr = Mock()
            asr.recognize_filetrans.return_value = AsrFixture([
                {'begin_time':0,'end_time':900,'text':'こんにちは'},
                {'begin_time':1000,'end_time':1900,'text':'ありがとう'}])
            translator = Mock()
            translator.chat_completions.side_effect = [
                ApiResult('fixture','[0001] merged',0,{},'id','stop'),
                ApiResult('fixture','你好',0,{},'id','stop'),
                ApiResult('fixture','谢谢',0,{},'id','stop'),
                ApiResult('fixture','[{"id":"0001","translation":"你好"},{"id":"0002","translation":"谢谢"}]',0,{},'id','stop')]
            with patch.object(pipeline.QwenAudioAsrClient,'from_environment',return_value=asr), patch.object(pipeline.DashScopeOpenAIClient,'from_environment',return_value=translator):
                with job_lock(output):
                    self.assertEqual(pipeline.execute_job(args),0)
            self.assertEqual(translator.chat_completions.call_count,4)
            video = next(output.glob('*.mp4'))
            before = video.stat().st_mtime_ns
            with patch.object(pipeline.QwenAudioAsrClient,'from_environment',side_effect=AssertionError('ASR must be cached')), patch.object(pipeline.DashScopeOpenAIClient,'from_environment',side_effect=AssertionError('MT must be cached')):
                with job_lock(output):
                    self.assertEqual(pipeline.execute_job(args),0)
            self.assertEqual(video.stat().st_mtime_ns,before)
            runs = list((output/'intermediates/runs').glob('*/run.json'))
            self.assertEqual(len(runs),2)
            self.assertTrue(all(json.loads(p.read_text())['status']=='complete' for p in runs))
            with job_lock(output):
                pass

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_FFMPEG'), 'opt-in local FFmpeg integration')
    def test_real_exports_are_versioned_resumable_and_nested(self):
        ffmpeg = Path(os.environ['RINAYAKI_TEST_FFMPEG'])
        with tempfile.TemporaryDirectory(prefix='RinaYaki spaces ') as directory:
            root = Path(directory)
            source = root / 'fixture.mp4'
            subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=1280x720:d=2', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(source)], check=True)
            cues = [{'id':'0001','start_ms':0,'end_ms':1900,'source_text':'こんにちは。元気ですか？','translation':'你好，今天过得怎么样？'}]
            output = root / 'job'
            details = output / 'intermediates'
            result = pipeline.export_and_mux(cues, source, details, ffmpeg=ffmpeg, stem='demo', output_dir=output)
            video = next(output.glob('*.mp4'))
            first = video.name
            before = video.stat().st_mtime_ns
            pipeline.export_and_mux(cues, source, details, ffmpeg=ffmpeg, stem='demo', output_dir=output)
            self.assertEqual(video.stat().st_mtime_ns, before)
            cues[0]['translation'] = '新的字幕版本'
            pipeline.export_and_mux(cues, source, details, ffmpeg=ffmpeg, stem='demo', output_dir=output)
            self.assertEqual(len(list(output.glob('*.mp4'))), 1)
            self.assertNotEqual(next(output.glob('*.mp4')).name, first)
            self.assertTrue((details / 'exports' / 'previous' / first).is_file())
            self.assertTrue(all((output / path).exists() for path in result.values() if not path.endswith('.mp4')))
            self.assertEqual({p.name for p in output.iterdir() if p.is_dir()}, {'intermediates'})
            before_style = next(output.glob('*.mp4')).name
            styled = pipeline.export_and_mux(cues, source, details, ffmpeg=ffmpeg, stem='demo', output_dir=output,
                                    speaker_styles={'unknown':{'color':'#9CA5B9'}})
            self.assertNotEqual(next(output.glob('*.mp4')).name,before_style)
            ass_path = next(output / path for path in styled.values() if path.endswith('.ass'))
            ass = ass_path.read_text(encoding='utf-8')
            self.assertGreaterEqual(ass.count(r'\3c&HB9A59C&'), 2)
            self.assertNotIn(r'\1c&HB9A59C&', ass)


if __name__ == '__main__':
    unittest.main()
