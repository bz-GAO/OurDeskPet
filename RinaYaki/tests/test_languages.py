import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rinayaki.languages import asr_hints, stored_languages, validate_languages, stored_speaker_count
from rinayaki.cloud_asr import filetrans_payload, CloudAsrResult
from rinayaki.translation import ApiResult
from rinayaki.settings import UserSettings
from rinayaki.subtitles import SubtitleDocument, SubtitleCue, export_subtitles, render_ass
from scripts import full_video_pipeline as pipeline


class LanguageTests(unittest.TestCase):
    def test_auto_and_legacy_defaults(self):
        self.assertNotIn('language_hints', filetrans_payload('https://example.com/a.wav', language_hints=asr_hints('auto'))['parameters'])
        self.assertEqual(filetrans_payload('https://example.com/a.wav',language_hints=asr_hints('en'))['parameters']['language_hints'], ['en'])
        self.assertEqual(stored_languages({}), ('ja','zh-Hans'))
        with self.assertRaises(ValueError):
            validate_languages('ja','auto')
        self.assertIsNone(stored_speaker_count({}))
        self.assertEqual(stored_speaker_count({'speaker_count':1}),1)
        with self.assertRaises(ValueError):
            stored_speaker_count({'speaker_count':0})

    def test_speaker_count_controls_diarization_and_cache(self):
        client=Mock()
        client.recognize_filetrans.return_value=CloudAsrResult('fixture','hello',(),{},0,None,{})
        with tempfile.TemporaryDirectory() as d, patch.object(pipeline.QwenAudioAsrClient,'from_environment',return_value=client):
            root=Path(d); audio=root/'audio.wav'; audio.write_bytes(b'fixture')
            for count in (None,1,1,2):
                pipeline.transcribe(audio,root,project_root=root,speaker_count=count)
            self.assertEqual(client.recognize_filetrans.call_count,3)
            self.assertTrue(client.recognize_filetrans.call_args_list[0].kwargs['diarization_enabled'])
            self.assertFalse(client.recognize_filetrans.call_args_list[1].kwargs['diarization_enabled'])
            self.assertEqual(client.recognize_filetrans.call_args_list[2].kwargs['speaker_count'],2)

    def test_asr_language_cache_and_auto_hint(self):
        client=Mock()
        client.recognize_filetrans.return_value=CloudAsrResult('fixture','hello',(),{},0,None,{})
        with tempfile.TemporaryDirectory() as d, patch.object(pipeline.QwenAudioAsrClient,'from_environment',return_value=client):
            root=Path(d); audio=root/'audio.wav';audio.write_bytes(b'fixture')
            for lang in ('auto','auto','en'):
                pipeline.transcribe(audio,root,project_root=root,source_language=lang)
            self.assertEqual(client.recognize_filetrans.call_count,2)
            self.assertEqual(client.recognize_filetrans.call_args_list[0].kwargs['language_hints'],())
            self.assertEqual(client.recognize_filetrans.call_args_list[1].kwargs['language_hints'],('en',))

    def test_translation_target_invalidates_cache_and_recovery_uses_pair(self):
        client=Mock()
        client.chat_completions.return_value=ApiResult('test','[0001] hello',0,{},'id','stop')
        source={'sentences':[{'begin_time':0,'end_time':1000,'text':'こんにちは'}]}
        with tempfile.TemporaryDirectory() as d, patch.object(pipeline.DashScopeOpenAIClient,'from_environment',return_value=client):
            root=Path(d)
            for target in ('en','en','ja'):
                pipeline.translate(source,root,project_root=root,batch_size=12,source_language='auto',target_language=target)
            self.assertEqual(client.chat_completions.call_count,2)
            first = client.chat_completions.call_args_list[0].args[0]['translation_options']
            self.assertEqual((first['source_lang'],first['target_lang']),('auto','English'))
            self.assertIn('subtitles',first['domains'])
            pipeline.recover_translation_batch(client,[{'id':'0001','source_text':'hello'}],root/'repairs',1,source_language='en',target_language='ja')
            repaired = client.chat_completions.call_args.args[0]['translation_options']
            self.assertEqual((repaired['source_lang'],repaired['target_lang']),('English','Japanese'))

    def test_configured_translation_model_reaches_provider_payload(self):
        client=Mock()
        client.chat_completions.return_value=ApiResult('test','[0001] hello',0,{},'id','stop')
        source={'sentences':[{'begin_time':0,'end_time':1000,'text':'こんにちは'}]}
        settings=UserSettings(api_key='sk-fixture',translation_model='qwen-mt-plus')
        with tempfile.TemporaryDirectory() as d, patch.object(pipeline.DashScopeOpenAIClient,'from_environment',return_value=client):
            pipeline.translate(source,Path(d),project_root=Path(d),settings=settings,batch_size=12)
        self.assertEqual(client.chat_completions.call_args.args[0]['model'],'qwen-mt-plus')

    def test_refinement_target_changes_prompt_and_cache(self):
        client=Mock()
        client.chat_completions.return_value=ApiResult('test','[{"id":"0001","translation":"hello"}]',0,{},'id','stop')
        cues=[{'id':'0001','source_text':'原文','draft_translation':'draft'}]
        with tempfile.TemporaryDirectory() as d, patch.object(pipeline.DashScopeOpenAIClient,'from_environment',return_value=client):
            for target in ('en','en','ja'):
                pipeline.refine(cues,Path(d),project_root=Path(d),batch_size=20,source_language='auto',target_language=target)
            self.assertEqual(client.chat_completions.call_count,2)
            self.assertIn('目标语言：Japanese',client.chat_completions.call_args.args[0]['messages'][0]['content'])

    def test_same_language_files_do_not_overwrite_and_japanese_font(self):
        doc=SubtitleDocument(source_language='ja',target_language='ja',cues=(SubtitleCue(cue_id='1',start_ms=0,end_ms=1000,source_text='原文',translation='校对'),))
        with tempfile.TemporaryDirectory() as d:
            first=export_subtitles(doc,Path(d),stem='test',formats=('srt',),mode='source')[0]
            second=export_subtitles(doc,Path(d),stem='test',formats=('srt',),mode='translated')[0]
            self.assertNotEqual(first,second)
            self.assertIn('原文',first.read_text(encoding='utf-8'))
            self.assertIn('校对',second.read_text(encoding='utf-8'))
        self.assertIn('Style: Translation,Noto Sans CJK JP Medium',render_ass(doc,mode='bilingual'))
