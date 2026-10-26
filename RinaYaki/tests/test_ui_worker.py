import json
import sys
from pathlib import Path
import tempfile
import os
import subprocess
import time
from dataclasses import dataclass
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_ui_job import run_job
from rinayaki.project_storage import create_cached_project, create_direct_project, control_path, write_local_json
from rinayaki.translation import ApiResult
import full_video_pipeline as pipeline


class WorkerTests(unittest.TestCase):
    def test_direct_export_keeps_project_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=create_direct_project(str(root),'我的项目',{'kind':'web','source':'https://example.com/video','title':'Fixture'},root/'cache',root/'.local/projects.json')
            with patch('run_ui_job.publish_locked_project',side_effect=AssertionError('no migration')):
                self.assertEqual(run_job(job,root/'cache','export',execute=self.export_fixture),0)
            self.assertTrue(job.is_dir())
            self.assertTrue((job/'我的项目.mp4').is_file())
            self.assertFalse((root/'cache').exists())
            self.assertEqual(json.loads(control_path(job,root/'cache').read_text())['status'],'complete')

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_FFMPEG') and os.name=='nt','Windows detached worker and FFmpeg required')
    def test_real_detached_export_finishes_after_launcher_exits(self):
        @dataclass
        class AsrFixture:
            sentences: list
        with tempfile.TemporaryDirectory(prefix='Yaki move ') as directory:
            root=Path(directory)
            source=root/'fixture.mp4'
            subprocess.run([os.environ['RINAYAKI_TEST_FFMPEG'],'-v','error','-f','lavfi','-i','color=c=gray:s=640x360:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
            cache=root/'cache'
            job=create_cached_project(cache,str(root),'最终项目',{'kind':'local','source':str(source),'title':'Fixture'})
            asr=Mock()
            asr.recognize_filetrans.return_value=AsrFixture([{'begin_time':0,'end_time':1900,'text':'こんにちは','speaker_id':0}])
            translator=Mock()
            translator.chat_completions.side_effect=[ApiResult('test','[0001] 你好',0,{},'id','stop'),ApiResult('test','[{"id":"0001","translation":"你好"}]',0,{},'id','stop')]
            with patch.object(pipeline.QwenAudioAsrClient,'from_environment',return_value=asr),patch.object(pipeline.DashScopeOpenAIClient,'from_environment',return_value=translator):
                self.assertEqual(run_job(job,cache,'prepare'),0)
            self.assertFalse(list(job.glob('*.mp4')))
            prepared=json.loads((job/'intermediates/prepared.json').read_text(encoding='utf-8'))
            write_local_json(job/'intermediates/styles.json',{'prepared_key':prepared['key'],'speakers':{'0':{'color':'#9CA5B9'}}})
            command=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/run_ui_job.py'),'--cache-root',str(cache),'--job-id',job.name,'--phase','export']
            launcher='import subprocess,sys; subprocess.Popen(sys.argv[1:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP)'
            subprocess.run([sys.executable,'-c',launcher,*command],check=True,timeout=10)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                state=json.loads(control_path(job,cache).read_text(encoding='utf-8'))
                if state['status'] in {'complete','failed'}:
                    break
                time.sleep(.1)
            self.assertEqual(state['status'],'complete',state)
            self.assertFalse(job.exists())
            final=root/'最终项目'
            self.assertEqual(len(list(final.glob('*.mp4'))),1)
            manifest=json.loads((final/'intermediates/pipeline.json').read_text(encoding='utf-8'))
            self.assertTrue(all((final/path).is_file() for path in manifest['outputs'].values()))

    def make_job(self, root):
        return create_cached_project(root/'cache',str(root),'我的项目',{'kind':'web','source':'https://example.com/video','title':'Fixture'})

    def export_fixture(self,args):
        self.assertEqual(args.phase,'export')
        self.assertEqual(args.stem,'我的项目')
        video=args.project_dir/'我的项目.mp4'
        video.write_bytes(b'fixture video')
        write_local_json(args.project_dir/'intermediates/pipeline.json',{'status':'complete','outputs':{'video':video.name}})
        print('fixture log preserved')
        return 0

    def test_export_publishes_and_preserves_closed_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=self.make_job(root)
            self.assertEqual(run_job(job,root/'cache','export',execute=self.export_fixture),0)
            self.assertFalse(job.exists())
            self.assertIn('fixture log preserved',(root/'我的项目/intermediates/launcher.log').read_text(encoding='utf-8'))
            self.assertEqual(json.loads(control_path(job,root/'cache').read_text())['status'],'complete')

    def test_retry_migration_never_reruns_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=self.make_job(root)
            with patch('rinayaki.project_storage.shutil.copytree',side_effect=OSError('disk full')):
                self.assertEqual(run_job(job,root/'cache','export',execute=self.export_fixture),1)
            control=json.loads(control_path(job,root/'cache').read_text())
            self.assertEqual(control['phase'],'publish')
            execute=Mock(side_effect=AssertionError('must not re-run a cloud/export stage'))
            self.assertEqual(run_job(job,root/'cache','publish',execute=execute),0)
            execute.assert_not_called()

    def test_prepared_resume_avoids_cloud_and_leaves_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=self.make_job(root)
            write_local_json(job/'intermediates/prepared.json',{'fixture':True})
            execute=Mock(side_effect=AssertionError('must not repeat preparation'))
            self.assertEqual(run_job(job,root/'cache','prepare',execute=execute),0)
            self.assertTrue(job.exists())
            self.assertFalse((root/'我的项目').exists())
            execute.assert_not_called()
