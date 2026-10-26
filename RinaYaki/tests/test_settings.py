import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from rinayaki.settings import apply_runtime_snapshot, load_settings, save_settings, default_output_dir
from rinayaki.settings import DEFAULT_ASR_MODEL, UserSettings, validate_settings


class UserSettingsTests(unittest.TestCase):
    def test_example_config_tracks_current_offline_model_and_excludes_live_settings(self):
        example = tomllib.loads(
            (Path(__file__).parents[1] / 'config' / 'rinayaki.example.toml').read_text(encoding='utf-8')
        )
        self.assertEqual(example['offline']['api_asr']['long_file_model'], DEFAULT_ASR_MODEL)
        self.assertNotIn('live', example)

    def test_default_output_follows_installation_and_keeps_custom_path(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'profile'
            with self.environment(home):
                expected = str(default_output_dir())
                self.assertEqual(load_settings().default_project_dir, expected)

                self.assertFalse((home / 'output').exists())
                chosen = Path(directory) / 'chosen'
                save_settings({'defaultProjectDir': str(chosen)})
                self.assertEqual(load_settings().default_project_dir, str(chosen.resolve()))
                save_settings({'defaultProjectDir': ''})
                self.assertEqual(load_settings().default_project_dir, expected)

    def test_release_default_output_stays_in_private_data_when_installation_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'profile'
            first, second = Path(directory) / 'first', Path(directory) / 'second'
            with self.environment(home):
                save_settings({'defaultProjectDir': str(default_output_dir(first))}, first)
                self.assertEqual(load_settings(second).default_project_dir, str(home / 'output'))

    def test_old_default_upgrades_but_project_snapshot_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            old = 'qwen-audio-3.0-asr-flash-filetrans'
            (home/'settings.json').write_text(json.dumps({'asr_model':old}),encoding='utf-8')
            with self.environment(home):
                loaded = load_settings()
                self.assertEqual(loaded.asr_model,DEFAULT_ASR_MODEL)
                snapshot = UserSettings(api_key='',asr_model=old).runtime_snapshot()
                self.assertEqual(apply_runtime_snapshot(loaded,snapshot).asr_model,old)
                # An explicit later selection of 3.0 is not silently migrated.
                save_settings({'asrModel':old})
                self.assertEqual(load_settings().asr_model,old)

    def test_live_engine_persists_without_changing_offline_translation(self):
        with tempfile.TemporaryDirectory() as directory, self.environment(Path(directory)):
            loaded = save_settings({'liveEngine':'livetranslate'})
            self.assertEqual(load_settings().live_engine,'livetranslate')
            self.assertEqual(loaded.public()['liveEngine'],'livetranslate')
            self.assertEqual(loaded.translation_model,'qwen-mt-flash')
            with self.assertRaises(ValueError):
                validate_settings(UserSettings(api_key='',live_engine='invalid'))

    def environment(self, home):
        return patch.dict(os.environ, {
            'RINAYAKI_CONFIG_HOME': str(home),
            'DASHSCOPE_API_KEY': '', 'DASHSCOPE_BASE_URL': '',
            'DASHSCOPE_HTTP_API_URL': '', 'DASHSCOPE_WEBSOCKET_URL': '',
            'DASHSCOPE_MIN_REQUEST_INTERVAL_SECONDS': '',
        }, clear=False)

    def test_user_secret_is_separate_and_never_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'user-config'
            projects = root / 'projects'
            projects.mkdir()
            with self.environment(home):
                saved = save_settings({
                    'apiKey': 'sk-private', 'minimumIntervalSeconds': 1.6,
                    'translationModel': 'qwen-mt-plus',
                    'defaultProjectDir': str(projects),
                }, root)
                public = saved.public()
                self.assertTrue(public['hasApiKey'])
                self.assertNotIn('apiKey', public)
                self.assertNotIn('sk-private', (home / 'settings.json').read_text(encoding='utf-8'))
                self.assertIn('sk-private', (home / 'credentials.env').read_text(encoding='utf-8'))
                loaded = load_settings(root)
                self.assertEqual(loaded.translation_model, 'qwen-mt-plus')
                self.assertEqual(loaded.default_project_dir, str(projects.resolve()))

    def test_project_snapshot_is_not_changed_by_later_user_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'user-config'
            with self.environment(home):
                first = save_settings({'apiKey': 'sk-key', 'translationModel': 'model-a'}, root)
                snapshot = first.runtime_snapshot()
                later = save_settings({'translationModel': 'model-b'}, root)
                resumed = apply_runtime_snapshot(later, snapshot)
                self.assertEqual(resumed.translation_model, 'model-a')
                self.assertEqual(resumed.api_key, 'sk-key')

    def test_repository_local_env_remains_read_only_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('DASHSCOPE_API_KEY=sk-legacy\n', encoding='utf-8')
            with self.environment(root / 'user-config'):
                self.assertTrue(load_settings(root).public()['hasApiKey'])
                save_settings({'minimumIntervalSeconds': 2}, root)
            self.assertEqual((root / '.env').read_text(encoding='utf-8'), 'DASHSCOPE_API_KEY=sk-legacy\n')


if __name__ == '__main__':
    unittest.main()
