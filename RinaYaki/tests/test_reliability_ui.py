import tempfile
from pathlib import Path
import unittest
import subprocess
import sys
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from rinayaki.retry import request_with_retry
from rinayaki.video_input import normalize_input
from rinayaki.cloud_asr import QwenAudioAsrClient
from rinayaki.job import job_lock


class ReliabilityTests(unittest.TestCase):
    def test_lock_releases_after_process_is_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            code = 'from pathlib import Path; from rinayaki.job import job_lock; import sys,time\nwith job_lock(Path(sys.argv[1])):\n print("locked",flush=True)\n time.sleep(60)'
            child = subprocess.Popen([sys.executable,'-u','-c',code,directory],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'locked')
                with self.assertRaises(RuntimeError):
                    with job_lock(Path(directory)):
                        pass
            finally:
                child.kill()
                child.wait(timeout=10)
                child.stdout.close()
            with job_lock(Path(directory)):
                pass

    def test_retry_read_and_rate_limit_but_not_ambiguous_post(self):
        operation = Mock(side_effect=[URLError('offline'), 'ok'])
        self.assertEqual(request_with_retry(operation,safe_read=True,sleep=lambda _:None),'ok')
        operation = Mock(side_effect=URLError('offline'))
        with self.assertRaises(URLError):
            request_with_retry(operation,sleep=lambda _:None)
        self.assertEqual(operation.call_count,1)
        operation = Mock(side_effect=HTTPError('x',429,'rate limit',{},None))
        waits = []
        with self.assertRaises(HTTPError):
            request_with_retry(operation,sleep=waits.append)
        self.assertEqual(operation.call_count,6)
        self.assertEqual(waits,[10,20,40,60,60])

    def test_rate_limit_retry_honours_server_delay_and_reports_wait(self):
        headers = {'Retry-After': '75'}
        operation = Mock(side_effect=[HTTPError('x',429,'rate limit',headers,None),'ok'])
        waits = []
        notices = []
        result = request_with_retry(operation,sleep=waits.append,
            on_retry=lambda attempt,delay,error:notices.append((attempt,delay,error.code)))
        self.assertEqual(result,'ok')
        self.assertEqual(waits,[75])
        self.assertEqual(notices,[(1,75,429)])

    def test_asr_resume_never_submits(self):
        client = QwenAudioAsrClient('test')
        callback = Mock()
        task = {'output':{'task_status':'SUCCEEDED','results':[{'subtask_status':'SUCCEEDED','transcription_url':'https://example.com/result'}]}}
        with patch.object(client,'_request_json',side_effect=[task,{'transcripts':[]}]) as request:
            client.recognize_filetrans('',resume_task_id='task1',on_submitted=callback)
        self.assertTrue(all(call.args[0]=='GET' for call in request.call_args_list))
        callback.assert_called_once_with('task1')

    def test_ids_links_and_rejection(self):
        expected = 'https://www.youtube.com/watch?v=kycUI2dAziw'
        for value in ['kycUI2dAziw','https://youtu.be/kycUI2dAziw?t=2','https://www.youtube.com/shorts/kycUI2dAziw']:
            self.assertEqual(normalize_input(value),('web',expected))
        self.assertEqual(normalize_input('BV1xx411c7mD')[1],'https://www.bilibili.com/video/BV1xx411c7mD')
        for value in ['', 'https://youtube.com/playlist?list=x', 'https://example.org/','--help']:
            with self.assertRaises(ValueError):
                normalize_input(value)
        self.assertEqual(normalize_input('https://example.org/video/123'), ('web', 'https://example.org/video/123'))
        # A lookalike host is a generic URL, never rewritten as YouTube.
        self.assertEqual(normalize_input('https://youtube.com.evil.org/watch?v=kycUI2dAziw')[1], 'https://youtube.com.evil.org/watch?v=kycUI2dAziw')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'空 格.mp4'
            source.touch()
            self.assertEqual(normalize_input(str(source)),('local',str(source.resolve())))
