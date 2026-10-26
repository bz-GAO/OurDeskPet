"""Web session validation and lifecycle without opening a real browser."""
import os
from http.cookies import SimpleCookie
from pathlib import Path
import queue
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rinayaki.web_session import launcher
from rinayaki.web_session.model import (
    profile_directory, session_target, validate_snapshot)
from rinayaki.web_session.runner import session_lock, write_cookie_snapshot


class WebSessionTests(unittest.TestCase):
    def test_supported_targets_are_canonical_and_site_scoped(self):
        youtube = session_target('tz5GxmVxdGU')
        self.assertEqual((youtube.site, youtube.url), (
            'youtube', 'https://www.youtube.com/watch?v=tz5GxmVxdGU'))
        bilibili = session_target(
            'https://www.bilibili.com/video/BV1xx411c7mD/?p=2&vd_source=private#reply')
        self.assertEqual(bilibili.url,
                         'https://www.bilibili.com/video/BV1xx411c7mD?p=2')
        with self.assertRaises(ValueError):
            session_target('https://user:secret@youtube.com/watch?v=tz5GxmVxdGU')
        generic = session_target('https://video.example/members/episode-one')
        self.assertEqual(generic.title, 'video.example')
        self.assertRegex(generic.site, r'^site-[0-9a-f]{16}$')

    def test_profiles_live_only_under_user_config(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'RINAYAKI_CONFIG_HOME': directory}):
            expected = Path(directory).resolve() / 'web_sessions' / 'mellowfan'
            self.assertEqual(profile_directory('mellowfan'), expected)
            with self.assertRaises(ValueError):
                profile_directory('../escape')

    @unittest.skipUnless(os.name == 'nt', 'Windows file locking')
    def test_one_process_owns_each_site_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'RINAYAKI_CONFIG_HOME': directory}):
            with session_lock('youtube'):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, '已经打开'):
                        with session_lock('youtube'):
                            pass
            with session_lock('youtube'):
                pass

    def test_launcher_uses_module_and_inherits_no_secret_arguments(self):
        fake = unittest.mock.Mock(spec=subprocess.Popen)
        with patch.object(launcher, 'can_open_session', return_value=True), \
             patch.object(launcher, '_responses', return_value=queue.Queue()), \
             patch.object(launcher.subprocess, 'Popen', return_value=fake) as popen:
            launched = launcher.launch_session('tz5GxmVxdGU')
        command = popen.call_args.args[0]
        self.assertEqual(launched.site, 'youtube')
        self.assertEqual(command[1:4], ['-m', 'rinayaki.web_session', '--source'])
        self.assertEqual(command[4], 'https://www.youtube.com/watch?v=tz5GxmVxdGU')
        self.assertNotIn('cookie', ' '.join(command).lower())

    def test_detached_launcher_keeps_profile_owned_by_yaki(self):
        fake = unittest.mock.Mock(spec=subprocess.Popen)
        fake.pid = 4321
        with patch.object(launcher, 'can_open_session', return_value=True), \
             patch.object(launcher.subprocess, 'Popen', return_value=fake) as popen:
            launched = launcher.launch_detached_session('tz5GxmVxdGU')
        command = popen.call_args.args[0]
        self.assertEqual(command[-2:], ['--source', 'https://www.youtube.com/watch?v=tz5GxmVxdGU'])
        self.assertEqual(popen.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(launched, {'site': 'youtube', 'title': 'YouTube', 'process_id': 4321})

    def test_cookie_snapshot_is_site_scoped_and_validated(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'RINAYAKI_CONFIG_HOME': directory}):
            target = session_target('https://www.bilibili.com/video/BV1xx411c7mD')
            cookie = SimpleCookie()
            cookie['SESSDATA'] = 'fixture-secret'
            cookie['SESSDATA']['domain'] = '.bilibili.com'
            cookie['SESSDATA']['path'] = '/'
            cookie['SESSDATA']['secure'] = True
            cookie['SESSDATA']['httponly'] = True
            path = write_cookie_snapshot(target, [cookie])
            try:
                self.assertEqual(validate_snapshot(target.url, path), path.resolve())
                text = path.read_text(encoding='utf-8')
                self.assertIn('#HttpOnly_.bilibili.com', text)
                with self.assertRaises(ValueError):
                    validate_snapshot('https://youtube.com/watch?v=tz5GxmVxdGU', path)
            finally:
                path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
