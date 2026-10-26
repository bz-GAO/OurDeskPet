"""Acquisition, app sessions and quality selection without network access."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from rinayaki import acquisition as ac


def metadata(height):
    return {'title': 'Video', 'duration': 2, 'formats': [
        {'height': h, 'vcodec': 'avc1', 'url': 'https://example.org/signed?secret=private'} for h in height]}


class AcquisitionTests(unittest.TestCase):
    def test_private_progress_marker_is_bounded(self):
        self.assertEqual(ac._progress_value('[download] rinayaki-progress: 42.5%'), 42.5)
        self.assertEqual(ac._progress_value('rinayaki-progress:999%'), 100.0)
        self.assertIsNone(ac._progress_value('https://example.org/private'))

    def test_streamed_download_reports_progress_without_returning_output(self):
        class Process:
            stdout = iter(['private extractor line\n', 'rinayaki-progress: 25.0%\n'])
            def poll(self): return None
            def wait(self, timeout=None): return 0
            def kill(self): pass
        values = []
        with patch.object(ac.subprocess, 'Popen', return_value=Process()):
            result = ac.checked_run(['yt-dlp'], 2, 'https://example.org/video',
                                    lambda completed, total: values.append((completed, total)))
        self.assertEqual(result.stdout, '')
        self.assertIn((25.0, 100.0), values)
        self.assertEqual(values[-1], (100.0, 100.0))

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'), 'opt-in native UI')
    def test_native_login_button_owns_webview_child_lifecycle(self):
        import sys
        import tkinter as tk
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import yaki_ui
        child = Mock()
        child.site = 'youtube'
        child.process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'RINAYAKI_CONFIG_HOME': directory}), \
             patch.object(yaki_ui, 'list_loopback_devices', return_value=[]), \
             patch.object(yaki_ui, 'can_open_session', return_value=True), \
             patch.object(yaki_ui, 'launch_session', return_value=child) as launch:
            window = tk.Tk()
            window.withdraw()
            app = yaki_ui.App(window)
            app.value.set('tz5GxmVxdGU')
            self.assertEqual(str(app.login_button['state']), 'normal')
            with patch.object(app, 'show_notice') as notice:
                app.open_login_window()
            launch.assert_called_once_with('tz5GxmVxdGU')
            notice.assert_called_once_with('登录窗口已打开。')
            app.close_window()
        child.close.assert_called_once_with()

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'), 'opt-in native UI')
    def test_locked_quality_menu_keeps_selection_and_exposes_hover_help(self):
        import sys
        import tkinter as tk
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import yaki_ui
        window = tk.Tk()
        window.withdraw()
        chosen = tk.StringVar(value='720P')
        locked = []
        picker = yaki_ui.QualityPicker(window, chosen, locked.append)
        picker.set_items([
            {'id': '720p', 'label': '720P', 'available': True},
            {'id': 'locked:bilibili:0', 'label': '1080P', 'available': False,
             'message': '登录后可检查此画质是否可用。'},
        ])
        try:
            self.assertEqual(picker.menu.entrycget(1, 'label'), '1080P  🔒')
            picker.menu.activate(1)
            picker._menu_hover()
            self.assertIsNotNone(picker.tooltip)
            picker.menu.invoke(1)
            self.assertEqual(chosen.get(), '720P')
            self.assertEqual(locked[0]['id'], 'locked:bilibili:0')
        finally:
            picker.destroy()
            window.destroy()

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'), 'opt-in native UI')
    def test_native_preview_enables_app_session_and_keeps_quality(self):
        import sys
        import tkinter as tk
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import yaki_ui
        calls = []
        def fake_preview(value, root, **kwargs):
            calls.append(value)
            return {'kind': 'web', 'source': 'https://example.org/video', 'title': 'Demo',
                    'duration': 1, 'thumbnail': None, 'qualities': [{'id': 'auto', 'label': '自动（最高可用）'}],
                    'acquisition': {'quality': 'auto', 'session': 'app'}}
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'RINAYAKI_CONFIG_HOME': directory}), \
             patch.object(yaki_ui, 'list_loopback_devices', return_value=[]), \
             patch.object(yaki_ui, 'preview', side_effect=fake_preview), patch.object(yaki_ui.threading, 'Thread', ImmediateThread):
            window = tk.Tk()
            window.withdraw()
            try:
                app = yaki_ui.App(window)
                app.value.set('BV1xx411c7mD')
                app.resolve(); app.poll()
                self.assertEqual(calls, ['BV1xx411c7mD'])
                self.assertEqual(app.source_record()['acquisition'], {
                    'quality': 'auto', 'session': 'app'})
            finally:
                for callback in window.tk.splitlist(window.tk.call('after', 'info')):
                    window.after_cancel(callback)
                window.destroy()

    def test_bilibili_tracking_is_removed_but_part_is_preserved(self):
        from rinayaki.video_input import normalize_input
        self.assertEqual(normalize_input('https://www.bilibili.com/video/BV1xx411c7mD/?p=2&vd_source=private&trackid=tracking')[1],
                         'https://www.bilibili.com/video/BV1xx411c7mD?p=2')

    def test_youtube_id_and_watch_url_share_one_canonical_source(self):
        from rinayaki.video_input import normalize_input
        expected = ('web', 'https://www.youtube.com/watch?v=tz5GxmVxdGU')
        self.assertEqual(normalize_input('tz5GxmVxdGU'), expected)
        self.assertEqual(normalize_input(
            'https://www.youtube.com/watch?v=tz5GxmVxdGU&list=ignored'), expected)

    def test_trial_is_not_accepted_as_full_video(self):
        with patch.object(ac.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps({**metadata([720]), 'is_preview': True}), '')):
            with self.assertRaisesRegex(ValueError, '试看'):
                ac.extract('https://example.org/video', Path('yt-dlp'))

    def test_damaged_extractor_json_does_not_expose_stdout(self):
        with patch.object(ac.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'private-invalid-json', '')):
            with self.assertRaisesRegex(ValueError, '^视频解析结果无效'):
                ac.extract('https://example.org/video', Path('yt-dlp'))

    def test_quality_validation_and_anonymous_command(self):
        for value in ({'quality': '720p/ba'}, {'quality': '-1p'}, []):
            with self.assertRaises(ValueError):
                ac.options(value)
        self.assertEqual(ac.options({'browser': 'edge', 'login_id': 'legacy'}), {
            'quality': 'auto', 'session': 'anonymous'})
        self.assertNotIn('--cookies-from-browser', ac.extractor_args())
        self.assertNotIn('--cookies', ac.extractor_args())
        with patch.object(ac.shutil, 'which', return_value='node.exe'):
            self.assertIn('--js-runtimes', ac.extractor_args(
                'https://www.youtube.com/watch?v=abcdefghijk'))
            self.assertNotIn('--js-runtimes', ac.extractor_args(
                'https://www.bilibili.com/video/BV1xx411c7mD'))
        self.assertEqual(ac.selector('1080p'),
                         'bv*[height=1080]+ba/bv*[width=1080]+ba/b[height=1080]/b[width=1080]')
        self.assertEqual(ac.selector('bili-q116'),
                         'bv*[quality=116]+ba/b[quality=116]')
    def test_login_required_error_is_short_and_does_not_expose_output(self):
        result = subprocess.CompletedProcess(
            [], 1, '', 'ERROR: Sign in required; cookie secret=value')
        with patch.object(ac.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(
                    ValueError, '^example.org 需要登录或订阅权限。$'):
                ac.extract('https://example.org/video', Path('yt-dlp'))

    def test_drm_audio_and_storyboards_not_listed(self):
        data = metadata([720])
        data['formats'] += [{'height': 1080, 'vcodec': 'av1', 'url': 'url', 'has_drm': True},
                            {'height': 90, 'vcodec': 'none', 'url': 'url'}]
        self.assertEqual([q['id'] for q in ac.qualities(data)], ['auto', '720p'])

    def test_generic_quality_uses_short_edge_for_vertical_video(self):
        data = {'formats': [
            {'width': 1080, 'height': 1920, 'vcodec': 'avc1', 'url': 'one'},
            {'width': 720, 'height': 1280, 'vcodec': 'avc1', 'url': 'two'},
        ]}
        self.assertEqual([(item['id'], item['label']) for item in ac.qualities(data)], [
            ('auto', '自动'), ('1080p', '1080P'), ('720p', '720P')])

    def test_locked_site_quality_is_visible_but_never_downloadable(self):
        data = metadata([720, 1080])
        data['_rinayaki_capabilities'] = {'locked_qualities': [{
            'id': 'locked:bilibili:0', 'label': '1080P', 'available': False,
            'message': '“1080P 高码率”需要会员权限。'}]}
        choices = ac.qualities(data)
        self.assertEqual([(item['label'], item['available']) for item in choices],
                         [('自动', True), ('1080P', True), ('720P', True),
                          ('1080P', False)])
        self.assertNotIn('locked:bilibili:0', {
            item['id'] for item in choices if item.get('available', True)})

    def test_playlists_and_live_rejected(self):
        for extra in ({'_type': 'playlist'}, {'entries': []}, {'is_live': True}):
            with patch.object(ac.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps({**metadata([720]), **extra}), '')):
                with self.assertRaisesRegex(ValueError, '单个'):
                    ac.extract('https://example.org/video', Path('yt-dlp'))

    def test_cache_separates_quality_and_source_but_ignores_withdrawn_login_fields(self):
        pairs = [('one', {}), ('two', {}), ('one', {'quality': '720p'})]
        self.assertEqual(len({ac.cache_key(source, policy) for source, policy in pairs}), 3)
        self.assertEqual(ac.cache_key('one', {}), ac.cache_key('one', {'browser': 'edge'}))

    def test_download_is_anonymous_checks_selection_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = []
            def run(command, **kwargs):
                commands.append(command)
                if '-o' in command:
                    Path(command[command.index('-o')+1].replace('%(ext)s', 'mkv')).write_bytes(b'video')
                return subprocess.CompletedProcess(command, 0, json.dumps(metadata([720, 1080])), '')
            policy = {'quality': '1080p'}
            with patch.object(ac.subprocess, 'run', side_effect=run):
                args = dict(executable=Path('yt-dlp'), ffmpeg=Path('ffmpeg'), policy=policy)
                target, saved = ac.acquire('https://example.org/video', root, **args)
                self.assertEqual(ac.acquire('https://example.org/video', root, **args)[0], target)
            self.assertEqual(len(commands), 2)
            self.assertTrue(all('--ignore-config' in command for command in commands))
            self.assertTrue(all('--cookies-from-browser' not in command and '--cookies' not in command for command in commands))
            self.assertIn('--check-formats', commands[-1])
            self.assertIn(ac.selector('1080p'), commands[-1])
            self.assertNotIn('secret', json.dumps(saved))

    def test_unavailable_resolution_fails_before_download(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ac, 'extract', return_value=metadata([360])), patch.object(ac.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, '画质'):
                ac.acquire('https://example.org/video', Path(tmp), executable=Path('yt-dlp'), ffmpeg=Path('ffmpeg'), policy={'quality': '1080p'})
            run.assert_not_called()

    def test_timeout_does_not_expose_url(self):
        with patch.object(ac.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['secret'], 90)):
            with self.assertRaisesRegex(ValueError, '^读取视频超时'):
                ac.extract('https://example.org/video?secret=private', Path('yt-dlp'))
