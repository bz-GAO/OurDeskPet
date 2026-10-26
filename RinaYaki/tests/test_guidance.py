import json
import os
from pathlib import Path
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from rinayaki.guidance import discover_packs, load_guidance
from rinayaki.translation import qwen_mt_payload, ApiResult
from rinayaki.live.session import LiveSettings, open_live_session
from rinayaki.live.coordinator import RealtimeCoordinator
from rinayaki.live import events
from rinayaki.settings import UserSettings
import yaki_ui


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root/'translation_guidance/packs/example'
        self.pack.mkdir(parents=True)
        self.manifest = {'schema_version':1,'pack_id':'example','name':'示例','version':'1',
                         'source_language':'ja','target_language':'zh-Hans','runtime_enabled':False,
                         'data_files':['cast.json'],'review_files':['nickname-candidates.json']}
        self.entries = [{'id':'cast.test','source':'田中ちえ美','target':'田中千惠美','match':'exact_name',
                         'aliases':[{'source':'ちぇみー','target':'切咪','match':'context_required'}]}]
        self.save()

    def save(self):
        (self.pack/'pack.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        (self.pack/'cast.json').write_text(json.dumps(self.entries),encoding='utf-8')

    def load(self):
        return load_guidance(self.root,['example'],'ja','zh-Hans',allow_draft=True)

    def test_opt_in_matching_context_and_expiration(self):
        with patch('rinayaki.guidance.discover_packs',side_effect=AssertionError('no disk scan')):
            self.assertEqual(load_guidance(self.root,[],'ja','zh-Hans').match('田中ちえ美'),[])
        with self.assertRaises(ValueError):
            load_guidance(self.root,['example'],'ja','zh-Hans')
        with self.assertRaises(ValueError):
            load_guidance(self.root,['example'],'en','ja',allow_draft=True)
        guidance = self.load()
        self.assertEqual(guidance.match('ちぇみー'),[])
        self.assertEqual(guidance.match('田中ちえ美です'),[{'source':'田中ちえ美','target':'田中千惠美'}])
        self.assertEqual(guidance.match('ちぇみーです'),[{'source':'ちぇみー','target':'切咪'}])
        guidance.match('普通の会話')
        self.assertEqual(guidance.match('ちぇみー'),[])
        self.assertEqual(len(guidance.provenance[0]['sha256']),64)
        self.assertEqual(self.load().match('田中 ちえ美です')[0]['target'],'田中千惠美')
        self.manifest['domain_hint']='These subtitles discuss the cast.'
        self.save()
        self.assertIn('cast',self.load().domain_hint)

    def test_conflicts_pending_and_path_escape(self):
        self.entries.append({'id':'other','source':'田中ちえ美','target':'错误','match':'exact_name'})
        self.save()
        self.assertEqual(self.load().match('田中ちえ美'),[])
        self.manifest['data_files']=['../escape.json']
        self.save()
        with self.assertRaises(ValueError):
            self.load()
        self.manifest['data_files']=['nickname-candidates.json']
        self.save()
        with self.assertRaises(ValueError):
            self.load()

    def test_terms_only_in_optional_field(self):
        text = '田中ちえ美です'
        plain = qwen_mt_payload(text)
        self.assertNotIn('terms',plain['translation_options'])
        guided = qwen_mt_payload(text,terms=self.load().match(text))
        self.assertEqual(guided['messages'],plain['messages'])
        self.assertEqual(guided['translation_options']['terms'][0]['target'],'田中千惠美')
        self.assertIn('cast',qwen_mt_payload(text,domain_hint='These subtitles discuss the cast.')['translation_options']['domains'])

    def test_live_phrases_exclude_contextual_and_conflicting_terms(self):
        guidance = self.load()
        self.assertEqual(guidance.static_phrases(),{'田中ちえ美':'田中千惠美'})
        self.entries.append({'id':'conflict','source':'田中ちえ美','target':'另一译法','match':'exact_name'})
        self.save()
        self.assertEqual(self.load().static_phrases(),{})

    def test_real_worker_passes_terms_and_provenance(self):
        live = LiveSettings(record_session=False,guidance_packs=('example',),allow_draft_guidance=True)
        paths = open_live_session(self.root,live)
        client = Mock()
        client.chat_completions_stream.side_effect = lambda payload,on_update,**kwargs: (on_update('田中千惠美') or ApiResult('qwen-mt-flash','田中千惠美',0,{},None,'stop'))
        done = threading.Event()
        bus = events.EventBus()
        bus.subscribe(lambda event:done.set() if event.kind==events.KIND_TRANSLATION else None)
        with patch('rinayaki.live.coordinator.QwenStreamingAsr'),patch('rinayaki.live.coordinator.WasapiLoopbackCapture'),patch('rinayaki.live.coordinator.translation.DashScopeOpenAIClient',return_value=client):
            coordinator = RealtimeCoordinator(live,UserSettings(api_key='test'),paths,bus=bus,guidance=self.load())
            try:
                coordinator.start()
                coordinator._accept_final('田中ちえ美です',0,100)
                self.assertTrue(done.wait(2))
                payload = client.chat_completions_stream.call_args.args[0]
                self.assertEqual(payload['translation_options']['terms'][0]['target'],'田中千惠美')
            finally:
                coordinator.stop()
        record = json.loads(paths.session_json.read_text('utf-8'))
        self.assertEqual(record['provenance']['guidance'][0]['pack_id'],'example')
        self.assertEqual(record['stats']['guidance_terms'],1)

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in GUI')
    def test_dialog_selection_language_switch_and_source_only(self):
        with patch.object(yaki_ui,'ROOT',self.root),patch.dict(os.environ,{'RINAYAKI_CONFIG_HOME':str(self.root/'config')}):
            window = tk.Tk()
            window.withdraw()
            try:
                app = yaki_ui.App(window)
                self.assertEqual(app.active_live_guidance(),[])
                app.open_live_guidance()
                app.live_guidance_choices['example'].set(True)
                app.apply_live_guidance_selection()
                self.assertEqual(app.active_live_guidance(),['example'])
                app.live_display_mode.set('只显示原文')
                self.assertEqual(app.active_live_guidance(),[])
                self.assertEqual(str(app.live_guidance_button['state']),'disabled')
                app.live_display_mode.set('双语显示')
                app.live_source_language.set('English')
                self.assertEqual(app.active_live_guidance(),[])
                app.live_source_language.set('日本語')
                self.assertEqual(app.active_live_guidance(),['example'])
                config={'source_language':'ja','target_language':'zh-Hans','display_mode':'bilingual',
                        'font_family':'Arial','subtitle_color':'#FFFFFF','guidance_packs':['example'],
                        'allow_draft_guidance':True}
                self.assertIn('--guidance-pack',yaki_ui.build_live_command('python',config))
                from rinayaki.live.__main__ import build_parser
                args = build_parser().parse_args(yaki_ui.build_live_command('python',config)[3:])
                self.assertEqual(args.guidance_pack,['example'])
                self.assertTrue(args.allow_draft_guidance)
                config['display_mode']='source'
                self.assertNotIn('--guidance-pack',yaki_ui.build_live_command('python',config))
            finally:
                for job in window.tk.call('after','info'):
                    window.after_cancel(job)
                window.destroy()
