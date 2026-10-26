"""Focused contract tests for the embedded desktop workflow."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import desk_bridge as bridge
from rinayaki.project_storage import set_control
from rinayaki.settings import UserSettings


class DeskBridgeTest(unittest.TestCase):
    def test_offline_preview_matches_native_pixels_and_shared_options(self):
        options = bridge.action('style_options', {})
        self.assertEqual(options['fonts'], [{'label': k, 'value': v} for k, v in bridge.FONTS.items()])
        pictures = []
        for font in bridge.FONTS.values():
            result = bridge.action('style_preview', {'text': '字幕预览 日本語 ABC', 'font': font, 'color': '#616D87'})
            with Image.open(io.BytesIO(base64.b64decode(result['image'].split(',')[1]))) as picture:
                native = bridge.render_style_preview('字幕预览 日本語 ABC', font_name=font,
                    fonts_directory=bridge.ROOT/'assets/fonts', outline_color='#616D87')
                self.assertEqual(picture.size, (720, 96))
                self.assertEqual(picture.tobytes(), native.tobytes())
                pictures.append(picture.tobytes())
        self.assertNotEqual(*pictures)
        for request in [{'text': 'x'*121}, {'text': []}, {'font': []}, {'font': '../font.ttf'}, {'color': []}, {'color': 'red'}]:
            with self.assertRaises(ValueError):
                bridge.action('style_preview', request)

    def test_scan_rejects_selected_link_before_resolving_it(self):
        selected = Path(__file__).resolve().parent / 'redirected-project'
        with patch.object(bridge, 'redirected', side_effect=lambda path: path == selected), \
                patch.object(Path, 'resolve', side_effect=AssertionError('link must be rejected before resolving')):
            with self.assertRaisesRegex(ValueError, '链接|联接'):
                bridge.scan_jobs(str(selected))

    def test_registered_link_cannot_be_followed_as_a_project(self):
        selected = Path(__file__).resolve().parent / 'redirected-project'
        with patch.object(bridge, 'redirected', side_effect=lambda path: path == selected), \
                patch.object(bridge, 'indexed_jobs', return_value=[selected]), \
                patch.object(bridge, 'write_local_json') as write:
            with self.assertRaisesRegex(ValueError, '链接|联接'):
                bridge.checked_job(str(selected))
            with tempfile.TemporaryDirectory() as folder, patch.object(bridge, 'INDEX', Path(folder) / 'projects.json'):
                bridge.register_jobs([selected])
                self.assertEqual(write.call_args.args[1], [])

    def test_one_provider_describes_two_independent_tools(self):
        description = bridge.bridge_description()
        self.assertEqual(description['protocol_version'], 1)
        self.assertEqual(description['provider']['id'], 'rinayaki')
        self.assertEqual([tool['id'] for tool in description['tools']], ['video', 'live'])
        self.assertTrue(description['tools'][0]['embedded_ready'])
        self.assertTrue(description['tools'][1]['embedded_ready'])

    def test_live_options_advertise_streaming_translation(self):
        with patch.object(bridge, 'list_loopback_devices', return_value=[]), patch.object(bridge, 'discover_packs', return_value=([], [])):
            options = bridge.live_options()
            self.assertTrue(options['translationStreaming'])
            self.assertEqual(options['colorPresets'][0],{'name':'默认','color':'#000000'})

    def test_live_start_uses_shared_engine_and_outline_style(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root/'.venv/Scripts/pythonw.exe'
            runtime.parent.mkdir(parents=True)
            runtime.touch()
            settings = UserSettings(api_key='fixture',live_engine='livetranslate')
            with patch.object(bridge,'ROOT',root), patch.object(bridge,'load_settings',return_value=settings), \
                 patch.object(bridge,'load_guidance'), patch.object(bridge.subprocess,'Popen',return_value=Mock(pid=1234)) as start:
                result = bridge.start_live({'guidancePacks':['example'],'allowDraftGuidance':True})
            self.assertEqual(result['processId'],1234)
            command = start.call_args.args[0]
            self.assertEqual(command[command.index('--translation-engine')+1],'livetranslate')
            self.assertEqual(command[command.index('--subtitle-color')+1],'#000000')
            self.assertIn('--guidance-pack',command)

    def test_live_style_preview_uses_bundled_font_without_file_write(self):
        result = bridge.action('live_style_preview',{'fontFamily':'Noto Sans CJK SC Medium',
            'fontSize':18,'subtitleColor':'#616D87','displayMode':'bilingual'})
        self.assertTrue(result['image'].startswith('data:image/png;base64,'))
        with Image.open(io.BytesIO(base64.b64decode(result['image'].split(',')[1]))) as picture:
            self.assertEqual(picture.width,720)
        with self.assertRaises(ValueError):
            bridge.action('live_style_preview',{'fontFamily':'Not Installed'})
        with self.assertRaises(ValueError):
            bridge.action('live_style_preview',{'fontFamily':[]})

    def test_settings_contract_never_returns_secret(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {
                'RINAYAKI_CONFIG_HOME': str(Path(folder) / 'config'),
                'DASHSCOPE_API_KEY': '', 'DASHSCOPE_BASE_URL': '',
                'DASHSCOPE_HTTP_API_URL': '', 'DASHSCOPE_WEBSOCKET_URL': '',
                'DASHSCOPE_MIN_REQUEST_INTERVAL_SECONDS': ''}, clear=False):
            result = bridge.action('settings_save', {'apiKey': 'sk-private', 'translationModel': 'qwen-mt-plus'})
            self.assertTrue(result['settings']['hasApiKey'])
            self.assertNotIn('apiKey', result['settings'])
            loaded = bridge.action('settings', {})['settings']
            self.assertEqual(loaded['translationModel'], 'qwen-mt-plus')
    def test_remote_thumbnail_becomes_webview_safe_data_url(self):
        stream = io.BytesIO()
        Image.new('RGB', (20, 10), '#c39aad').save(stream, format='JPEG')

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, *_): return stream.getvalue()

        metadata = {'kind': 'web', 'source': 'https://www.bilibili.com/video/BV1nmYS6FEq1',
                    'title': 'video', 'duration': 10.0, 'thumbnail': 'https://example.com/cover.jpg',
                    'acquisition': {'quality': 'auto', 'session': 'app'},
                    'capabilities': {'site': 'bilibili'}, 'qualities': [
                        {'id': '720p', 'label': '720P', 'available': True},
                        {'id': 'locked:bilibili:0', 'label': '4K', 'available': False}]}
        with patch.object(bridge, 'preview', return_value=metadata) as preview_call, patch.object(bridge, 'urlopen', return_value=Response()):
            result = bridge.video_preview('BV1nmYS6FEq1')
        self.assertTrue(result['thumbnail'].startswith('data:image/jpeg;base64,'))
        self.assertTrue(base64.b64decode(result['thumbnail'].split(',', 1)[1]).startswith(b'\xff\xd8'))
        self.assertEqual([item['id'] for item in result['qualities']], ['720p'])
        self.assertEqual(result['acquisition']['session'], 'app')
        self.assertNotIn('capabilities', result)
        preview_call.assert_called_once_with('BV1nmYS6FEq1', bridge.ROOT, use_app_session=True)

    def test_web_session_open_is_delegated_to_yaki(self):
        with patch.object(bridge, 'launch_detached_session', return_value={
                'site': 'bilibili', 'title': '哔哩哔哩', 'process_id': 1234}) as launch:
            result = bridge.action('web_session_open', {
                'value': 'https://www.bilibili.com/video/BV1xx411c7mD'})
        launch.assert_called_once_with('https://www.bilibili.com/video/BV1xx411c7mD')
        self.assertEqual(result, {'opened': True, 'site': 'bilibili', 'title': '哔哩哔哩'})

    def test_direct_project_can_reach_style_and_export_without_opening_native_ui(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / 'source.mp4'
            video.write_bytes(b'fixture')
            parent = root / 'projects'
            parent.mkdir()
            with patch.object(bridge, 'INDEX', root / 'index/projects.json'), patch.object(bridge, 'RUNS', root / 'cache'), patch.object(bridge, 'start_worker') as start:
                result = bridge.action('create', {'video': {'kind': 'local', 'source': str(video), 'title': 'source'},
                    'parent': str(parent), 'name': 'translated', 'sourceLanguage': 'ja', 'targetLanguage': 'zh-Hans'})
                job = Path(result['job'])
                self.assertTrue(job.is_dir())
                start.assert_called_once_with(job, 'prepare')
                self.assertEqual(bridge.action('jobs', {'source': str(video)})['jobs'][0]['job'], str(job))
                prepared = {'key': 'prepared-key', 'speakers': {'speaker-1': {'start_ms': 0, 'length_ms': 1000, 'text': 'test'}}}
                (job / 'intermediates/prepared.json').write_text(json.dumps(prepared), encoding='utf-8')
                set_control(job, bridge.RUNS, status='awaiting_style', phase='prepare')
                bridge.action('export', {'job': str(job), 'styles': {'speaker-1': {'color': '#FFFFFF'}}})
                styles = json.loads((job / 'intermediates/styles.json').read_text(encoding='utf-8'))
                self.assertEqual(styles['prepared_key'], 'prepared-key')
                self.assertEqual(start.call_args.args, (job, 'export'))

    def test_scan_discovers_and_registers_projects_created_outside_desk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.mp4'
            source.write_bytes(b'fixture')
            projects = root / 'projects'
            projects.mkdir()
            index = root / 'desk-index/projects.json'
            runs = root / 'cache'
            native_index = root / 'native-index/projects.json'
            job = bridge.create_direct_project(str(projects), 'native-project', {
                'kind': 'local', 'source': str(source), 'title': 'native',
                'source_language': 'ja', 'target_language': 'zh-Hans'
            }, runs, native_index)
            (projects / 'ordinary-folder').mkdir()

            with patch.object(bridge, 'INDEX', index), patch.object(bridge, 'RUNS', runs):
                result = bridge.action('scan', {'parent': str(projects)})
                self.assertTrue(result['canCreate'])
                self.assertEqual([item['job'] for item in result['jobs']], [str(job)])
                self.assertEqual(bridge.checked_job(str(job)), job.resolve())
                self.assertEqual(json.loads(index.read_text(encoding='utf-8')), [str(job.resolve())])


if __name__ == '__main__':
    unittest.main()
