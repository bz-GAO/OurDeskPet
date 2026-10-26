import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave

from rinayaki.live import events as ev
from rinayaki.live.coordinator import RealtimeCoordinator
from rinayaki.live.session import LiveSettings, open_live_session
from rinayaki.live.sinks.subtitle_window import SubtitleWindow
from rinayaki.settings import UserSettings


class FakeAsr:
    instances = []

    def __init__(self,*args,**kwargs):
        self.callbacks = kwargs
        self.sent = []
        self.stopped = False
        self.instances.append(self)

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def send(self,pcm):
        self.sent.append(pcm)


class FakeCapture(FakeAsr):
    instances = []


class LivePauseTests(unittest.TestCase):
    def test_pause_excludes_audio_and_resume_keeps_ids_and_recording_clock(self):
        FakeAsr.instances.clear()
        FakeCapture.instances.clear()
        with tempfile.TemporaryDirectory() as directory, \
             patch('rinayaki.live.coordinator.QwenStreamingAsr',FakeAsr), \
             patch('rinayaki.live.coordinator.WasapiLoopbackCapture',FakeCapture), \
             patch('rinayaki.live.coordinator.translation.DashScopeOpenAIClient',
                   side_effect=AssertionError('source-only must not translate')):
            live = LiveSettings(record_session=True,display_mode='source')
            paths = open_live_session(Path(directory),live,'pause')
            bus = ev.EventBus()
            events = []
            paused = threading.Event()
            resumed = threading.Event()
            def receive(event):
                events.append(event)
                if event.kind == ev.KIND_SESSION_PAUSED:
                    paused.set()
                if event.kind == ev.KIND_SESSION_RESUMED:
                    resumed.set()
            bus.subscribe(receive)
            coordinator = RealtimeCoordinator(live,UserSettings(api_key='test'),paths,bus=bus)
            try:
                coordinator.start()
                first = FakeAsr.instances[0]
                capture = FakeCapture.instances[0]
                capture.callbacks['on_block'](b'\0'*32000)
                first.callbacks['on_final']('before',0,1000)
                coordinator.request_pause(True)
                self.assertTrue(paused.wait(2))
                self.assertTrue(first.stopped)
                self.assertTrue(capture.stopped)
                self.assertFalse(coordinator.stopped)
                capture.callbacks['on_block'](b'\0'*32000)
                coordinator._on_audio_block(b'\0'*32000)
                first.callbacks['on_final']('stale',0,1000)
                self.assertEqual(coordinator.stats['audio_blocks'],1)
                self.assertEqual(coordinator.stats['finals'],1)
                self.assertEqual(json.loads(paths.session_json.read_text('utf-8'))['status'],'paused')
                coordinator.request_pause(False)
                self.assertTrue(resumed.wait(2))
                second = FakeAsr.instances[1]
                capture.callbacks['on_block'](b'\0'*32000)  # Old capture after resume is rejected.
                FakeCapture.instances[1].callbacks['on_block'](b'\0'*16000)
                second.callbacks['on_final']('after',0,500)
                self.assertEqual(len(second.sent),1)
                finals = [event for event in events if event.kind==ev.KIND_FINAL_TRANSCRIPT]
                self.assertEqual([e.payload['segment_id'] for e in finals],['live-000001','live-000002'])
                self.assertEqual(finals[1].payload['start_ms'],1000)
                self.assertEqual(finals[1].payload['end_ms'],1500)
                paused.clear()
                coordinator.request_pause(True)
                self.assertTrue(paused.wait(2))
                coordinator.stop('close-while-paused')
                with wave.open(str(paths.audio_wav),'rb') as recording:
                    self.assertEqual(recording.getnframes(),24000)
                self.assertEqual(coordinator.stats['translations'],0)
            finally:
                coordinator.stop('test-cleanup')

    def test_resume_failure_ends_and_persists_session(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('rinayaki.live.coordinator.QwenStreamingAsr',FakeAsr), \
             patch('rinayaki.live.coordinator.WasapiLoopbackCapture',FakeCapture):
            live = LiveSettings(record_session=False,display_mode='source')
            paths = open_live_session(Path(directory),live,'failure')
            coordinator = RealtimeCoordinator(live,UserSettings(api_key='test'),paths,bus=ev.EventBus())
            coordinator.start()
            coordinator._change_pause(True)
            with patch.object(FakeAsr,'start',side_effect=RuntimeError('offline')):
                coordinator._change_pause(False)
            self.assertTrue(coordinator.stopped)
            self.assertEqual(json.loads(paths.session_json.read_text('utf-8'))['ended_reason'],'pause-resume-failed')


@unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in native UI')
class LivePauseUiTests(unittest.TestCase):
    def test_pause_preserves_view_and_only_close_destroys(self):
        pause, close = Mock(), Mock()
        window = SubtitleWindow(on_pause=pause,on_close=close)
        window._root.withdraw()
        try:
            window._apply(ev.session_started('test',{}))
            window._apply(ev.final_transcript('1','原文',0,1))
            window._toggle_pause()
            pause.assert_called_once_with(True)
            close.assert_not_called()
            window._apply(ev.LiveEvent(ev.KIND_SESSION_PAUSED))
            self.assertEqual(window._pause_button['text'],'继续')
            self.assertEqual(len(window._history),1)
            window._apply(ev.translation('1','译文','原文','mock',0))
            self.assertEqual(window._history[0]['translation'],'译文')
            window._toggle_pause()
            pause.assert_called_with(False)
            window._apply(ev.LiveEvent(ev.KIND_SESSION_RESUMED))
            self.assertEqual(window._pause_button['text'],'暂停')
            window._set_display_mode('translation')
            self.assertEqual(window._mode_button['text'],'译文 ▾')
            with patch.object(window._root,'destroy') as destroy:
                window._apply(ev.session_ended('error',{}))
                window._root.update_idletasks()
                destroy.assert_not_called()
                window._handle_close()
                destroy.assert_called_once()
        finally:
            for job in window._root.tk.call('after','info'):
                window._root.after_cancel(job)
            window._root.destroy()

    def test_source_only_cannot_enable_translation_and_close_requests_cleanup(self):
        close = Mock()
        window = SubtitleWindow(display_mode='source',on_close=close,on_pause=Mock())
        window._root.withdraw()
        try:
            self.assertEqual(str(window._mode_button['state']),'disabled')
            window._set_display_mode('bilingual')
            self.assertEqual(window._display_mode,'source')
            window._handle_close()
            close.assert_called_once_with('window-stop')
            with patch.object(window._root,'destroy') as destroy:
                window._apply(ev.session_ended('window-stop',{}))
                window._root.update_idletasks()
                destroy.assert_called_once()
        finally:
            for job in window._root.tk.call('after','info'):
                window._root.after_cancel(job)
            window._root.destroy()
