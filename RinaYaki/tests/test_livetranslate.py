"""No paid requests: protocol, isolation, lifecycle and subtitle regressions."""
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from rinayaki.live import events as ev
from rinayaki.live.coordinator import RealtimeCoordinator
from rinayaki.live.livetranslate import LiveTranslate, MODEL, realtime_url, session_update
from rinayaki.live.session import LiveSettings, open_live_session
from rinayaki.live.sinks.console import ConsoleSink
from rinayaki.live.sinks.subtitle_window import SubtitleWindow
from rinayaki.settings import UserSettings


class FakeSocket:
    def __init__(self, text_only=True):
        self.messages = []
        self.closed = False
        self.events = queue.Queue()
        self.text_only = text_only

    def send(self, message):
        payload = json.loads(message)
        self.messages.append(payload)
        if payload['type']=='session.update':
            self.events.put({'type':'session.updated','session':{
                'output_modalities':['text'] if self.text_only else ['text','audio']}})
        elif payload['type']=='session.finish':
            self.events.put({'type':'conversation.item.input_audio_transcription.completed',
                             'item_id':'last','transcript':'最后一段'})
            self.events.put({'type':'session.finished'})

    def recv(self):
        import websocket
        try:
            value = self.events.get(timeout=.05)
        except queue.Empty:
            raise websocket.WebSocketTimeoutException()
        return json.dumps(value) if value is not None else ''

    def settimeout(self, value):
        pass

    def close(self):
        self.closed = True
        self.events.put(None)


class ProtocolTests(unittest.TestCase):
    def client(self, **kwargs):
        self.captions, self.usages, self.errors = [], [], []
        return LiveTranslate('fixture-secret','wss://dashscope.aliyuncs.com/api-ws/v1/inference',
            target_language='zh-Hans',on_caption=lambda *args:self.captions.append(args),
            on_usage=self.usages.append,on_error=self.errors.append,**kwargs)

    def test_endpoint_preserves_provider_and_text_only_config(self):
        self.assertEqual(realtime_url('wss://provider.example/api-ws/v1/inference'),
                         'wss://provider.example/api-ws/v1/realtime?model='+MODEL)
        self.assertEqual(session_update('zh-Hans')['session']['output_modalities'],['text'])
        self.assertEqual(session_update('zh-Hans')['session']['audio']['output']['voice'],'Tina')
        self.assertEqual(session_update('ja')['session']['translation']['language'],'ja')
        self.assertEqual(session_update('zh-Hans',{'田中ちえ美':'田中千惠美'})['session']['translation']['corpus']['phrases'],
                         {'田中ちえ美':'田中千惠美'})
        for url in ('ws://provider.example/inference','wss://key@provider.example/inference',
                    'wss://provider.example/unrecognized'):
            with self.assertRaises(ValueError):
                realtime_url(url)

    def test_interleaved_streams_complete_in_place_not_fifo_paired(self):
        client = self.client()
        client.handle_event({'type':'input_audio_buffer.speech_started','item_id':'source1',
                             'audio_start_ms':20,'speaker_id':1})
        client.handle_event({'type':'conversation.item.input_audio_transcription.delta',
                             'item_id':'source1','delta':'はい'})
        client.handle_event({'type':'response.text.delta','item_id':'answer1','delta':'你'})
        client.handle_event({'type':'response.text.delta','item_id':'answer1','delta':'好',
                             'event_id':'unique'})
        client.handle_event({'type':'response.text.delta','item_id':'answer1','delta':'好',
                             'event_id':'unique'})
        client.handle_event({'type':'conversation.item.input_audio_transcription.completed',
                             'item_id':'source1','transcript':'はい。'})
        client.handle_event({'type':'response.text.done','item_id':'answer1','text':'你好。'})
        client.handle_event({'type':'response.text.done','item_id':'answer1','text':'重复'})
        self.assertEqual([row[2] for row in self.captions],['はい','你','你好','はい。','你好。'])
        self.assertEqual(self.captions[0][0],'source-source1')
        self.assertEqual(self.captions[1][0],'translation-answer1')
        self.assertEqual(self.captions[0][3],20)
        self.assertEqual(self.captions[0][-1],1)

    def test_usage_response_fallback_and_error_are_safe(self):
        client = self.client()
        client.handle_event({'type':'response.done','response':{'status':'completed',
            'usage':{'input_tokens':70,'output_tokens':3},
            'output':[{'id':'reply','content':[{'type':'text','text':'你好'}]}]}})
        self.assertEqual(self.captions[-1][2],'你好')
        self.assertTrue(self.captions[-1][5])
        self.assertEqual(self.usages[0]['input_tokens'],70)
        client.handle_event({'type':'error','error':{'message':'fixture-secret'}})
        self.assertNotIn('fixture-secret',str(self.errors))

    def test_connect_configure_send_finish_and_close(self):
        socket = FakeSocket()
        connect = Mock(return_value=socket)
        client = self.client(connect=connect,finish_timeout=.5)
        client.start()
        client.send(b'\0'*3200)
        client.stop()
        client.stop()
        self.assertEqual([m['type'] for m in socket.messages],
                         ['session.update','input_audio_buffer.append','session.finish'])
        self.assertTrue(socket.closed)
        self.assertEqual(self.captions[-1][2],'最后一段')
        self.assertFalse(client._thread.is_alive())

    def test_audio_mode_not_confirmed_never_sends_audio(self):
        socket = FakeSocket(text_only=False)
        client = self.client(connect=Mock(return_value=socket))
        with self.assertRaises(RuntimeError):
            client.start()
        self.assertTrue(socket.closed)
        self.assertEqual(len(socket.messages),1)

    def test_start_and_finish_errors_always_close(self):
        client = self.client(connect=Mock(side_effect=RuntimeError('fixture-secret')))
        with self.assertRaises(RuntimeError) as caught:
            client.start()
        self.assertNotIn('fixture-secret',str(caught.exception))
        socket = FakeSocket()
        client = self.client(finish_timeout=.01)
        client._socket = socket
        with self.assertRaisesRegex(RuntimeError,'超时'):
            client.stop()
        self.assertTrue(socket.closed)


class CoordinatorTests(unittest.TestCase):
    def test_selected_backend_isolated_and_source_only_remains_asr(self):
        from test_live_pause import FakeAsr, FakeCapture
        with tempfile.TemporaryDirectory() as directory, \
             patch('rinayaki.live.coordinator.LiveTranslate',FakeAsr), \
             patch('rinayaki.live.coordinator.QwenStreamingAsr',FakeAsr), \
             patch('rinayaki.live.coordinator.WasapiLoopbackCapture',FakeCapture), \
             patch('rinayaki.live.coordinator.translation.DashScopeOpenAIClient') as mt:
            for mode in ('bilingual','source'):
                FakeAsr.instances.clear()
                live = LiveSettings(record_session=False,translation_engine='livetranslate',display_mode=mode)
                paths = open_live_session(Path(directory),live)
                events = []
                bus = ev.EventBus()
                bus.subscribe(events.append)
                coordinator = RealtimeCoordinator(live,UserSettings(api_key='test'),paths,bus=bus)
                coordinator.start()
                callbacks = FakeAsr.instances[0].callbacks
                if mode=='bilingual':
                    self.assertIn('on_caption',callbacks)
                    callbacks['on_caption']('id','translation','你好',0,100,False,None)
                    callbacks['on_caption']('id','translation','你好。',0,100,True,None)
                    callbacks['on_usage']({'input_tokens':70,'output_tokens':3})
                    self.assertIsNone(coordinator._translation_queue)
                    self.assertEqual(coordinator.stats['translations'],1)
                else:
                    self.assertIn('on_final',callbacks)
                    self.assertNotIn('on_caption',callbacks)
                coordinator.stop()
                record = json.loads(paths.session_json.read_text('utf-8'))
                self.assertEqual(record['provenance']['translation_model'],MODEL if mode=='bilingual' else None)
                if mode=='bilingual':
                    self.assertIn('你好。',paths.transcript_txt.read_text('utf-8'))
                    self.assertEqual(record['stats']['usage']['input_tokens'],70)
            mt.assert_not_called()

    def test_pause_resume_offsets_reject_stale_captions_and_drains_stop(self):
        from test_live_pause import FakeAsr, FakeCapture
        FakeAsr.instances.clear()
        with tempfile.TemporaryDirectory() as directory, \
             patch('rinayaki.live.coordinator.LiveTranslate',FakeAsr), \
             patch('rinayaki.live.coordinator.WasapiLoopbackCapture',FakeCapture):
            live = LiveSettings(record_session=False,translation_engine='livetranslate')
            paths = open_live_session(Path(directory),live)
            coordinator = RealtimeCoordinator(live,UserSettings(api_key='test'),paths,bus=ev.EventBus())
            coordinator.start()
            first = FakeAsr.instances[0]
            coordinator._on_audio_block(b'\0'*32000)
            first.callbacks['on_caption']('a','source','前',0,1000,True,0)
            coordinator._change_pause(True)
            coordinator._change_pause(False)
            first.callbacks['on_caption']('stale','source','过期',0,1000,True,0)
            second = FakeAsr.instances[1]
            second.callbacks['on_caption']('a','source','后',0,500,True,0)
            # Last response may arrive only during session.finish.
            second.stop = lambda: second.callbacks['on_caption']('b','translation','结束',0,500,True,None)
            coordinator.stop()
            transcript = paths.transcript_txt.read_text('utf-8')
            self.assertNotIn('过期',transcript)
            self.assertIn('结束',transcript)
            self.assertEqual(coordinator._segments[1]['start_ms'],1000)
            self.assertEqual(len({item['segment_id'] for item in coordinator._segments}),3)

    def test_terminology_can_be_enabled_with_livetranslate(self):
        self.assertEqual(LiveSettings(translation_engine='livetranslate',guidance_packs=('example',)).guidance_packs,('example',))
        self.assertFalse(LiveSettings(translation_engine='livetranslate',display_mode='source').uses_livetranslate)

    def test_caption_updates_do_not_duplicate_history_and_console_final(self):
        window = SubtitleWindow.__new__(SubtitleWindow)
        window._history = []
        window._history_limit = 8
        output = io.StringIO()
        sink = ConsoleSink(output)
        for final,text in ((False,'你'),(False,'你好'),(True,'你好。')):
            event = ev.caption_updated('reply','translation',text,0,100,final)
            window._apply(event)
            sink.handle(event)
        self.assertEqual(len(window._history),1)
        self.assertEqual(window._history[0]['translation'],'你好。')
        self.assertEqual(output.getvalue(),'你好。\n')


if __name__=='__main__':
    unittest.main()
