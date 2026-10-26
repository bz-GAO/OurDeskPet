import json
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import numpy as np

from rinayaki import settings as settings_module
from rinayaki.live import events as ev
from rinayaki.live.capture import CaptureError
from rinayaki.live.capture import wasapi_loopback
from rinayaki.live.coordinator import BoundedChannel, RealtimeCoordinator
from rinayaki.live.session import LiveSettings, open_live_session
from rinayaki.live.sinks.console import ConsoleSink
from rinayaki.live.sinks.subtitle_window import SubtitleWindow
from rinayaki.translation import ApiResult


class LiveSettingsAndSessionTests(unittest.TestCase):
    def test_live_only_limits_are_validated(self):
        self.assertEqual(LiveSettings().subtitle_font_size, 14)
        with self.assertRaisesRegex(ValueError, "字幕字号"):
            LiveSettings(subtitle_font_size=9)
        with self.assertRaisesRegex(ValueError, "翻译队列"):
            LiveSettings(translation_queue_capacity=0)
        with self.assertRaisesRegex(ValueError, "显示模式"):
            LiveSettings(display_mode="refined")
        with self.assertRaisesRegex(ValueError, "颜色"):
            LiveSettings(subtitle_color="white")

    def test_session_is_immediately_discoverable_and_collision_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = LiveSettings(record_session=False)
            first = open_live_session(root, settings, "same/name")
            second = open_live_session(root, settings, "same/name")

            self.assertNotEqual(first.root, second.root)
            self.assertTrue(second.root.name.startswith(first.root.name))
            record = json.loads(first.session_json.read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "created")
            self.assertIsNone(record["paths"]["audio"])


class LivePrimitiveTests(unittest.TestCase):
    def test_console_sink_obeys_display_mode(self):
        source = ev.final_transcript("live-1", "原文", 0, 1)
        translated = ev.translation("live-1", "译文", "原文", "model", 0.1)

        source_stream = io.StringIO()
        source_sink = ConsoleSink(source_stream, "source")
        source_sink.handle(source)
        source_sink.handle(translated)
        self.assertEqual(source_stream.getvalue(), "原文\n")

        translation_stream = io.StringIO()
        translation_sink = ConsoleSink(translation_stream, "translation")
        translation_sink.handle(source)
        translation_sink.handle(translated)
        self.assertEqual(translation_stream.getvalue(), "  译文\n")

    def test_bounded_channel_drops_oldest_and_rejects_after_close(self):
        dropped = []
        channel = BoundedChannel(2, dropped.append)
        self.assertTrue(channel.put("one"))
        self.assertTrue(channel.put("two"))
        self.assertFalse(channel.put("three"))
        self.assertEqual(dropped, ["one"])
        self.assertEqual(channel.get(0), "two")
        channel.close(discard=True)
        self.assertIsNone(channel.get(0))
        self.assertFalse(channel.put("late"))

    def test_audio_conversion_is_16k_mono_int16(self):
        stereo = np.column_stack((np.ones(480), np.zeros(480))).astype(np.float32)
        result = wasapi_loopback._to_16k_mono_int16(stereo, 48_000)
        self.assertEqual(len(result), 160 * 2)
        self.assertEqual(wasapi_loopback._to_16k_mono_int16(np.array([]), 48_000), b"")

    def test_named_device_must_be_loopback(self):
        class Device:
            def __init__(self, name, device_id, loopback):
                self.name = name
                self.id = device_id
                self.isloopback = loopback

        output = Device("Speakers Mix", "output", True)
        microphone = Device("Microphone", "input", False)
        backend = mock.Mock()
        backend.all_microphones.return_value = [microphone, output]
        with mock.patch.object(wasapi_loopback, "_soundcard", return_value=backend):
            self.assertIs(wasapi_loopback._resolve_device("speakers"), output)
            with self.assertRaises(CaptureError):
                wasapi_loopback._resolve_device("input")

    def test_event_timestamp_is_creation_time_not_serialization_time(self):
        event = ev.notice("ready")
        original = event.timestamp
        with mock.patch("rinayaki.live.events.time.time", return_value=original + 10):
            self.assertEqual(event.to_json()["ts"], original)


class SubtitleCorrelationTests(unittest.TestCase):
    def test_partial_translation_updates_in_place_and_survives_late_error(self):
        window = SubtitleWindow.__new__(SubtitleWindow)
        window._history = [{"segment_id": "live-1", "source": "原文", "translation": ""}]
        window._partial = None
        window._status = ""
        window._error = None
        window._apply(ev.translation_partial("live-1", "正在翻"))
        self.assertEqual(window._history[0]["translation"], "正在翻")
        window._apply(ev.translation_error("live-1", "network"))
        self.assertEqual(window._history[0]["translation"], "正在翻（未完成）")

    def test_old_skipped_segment_does_not_mark_latest_duplicate_text(self):
        window = SubtitleWindow.__new__(SubtitleWindow)
        window._history = [
            {"segment_id": "live-1", "source": "はい", "translation": ""},
            {"segment_id": "live-2", "source": "はい", "translation": ""},
        ]
        window._partial = None
        window._status = ""
        window._error = None

        window._apply(ev.translation_skipped("live-1", "拥堵"))

        self.assertEqual(window._history[0]["translation"], "（跳过）")
        self.assertEqual(window._history[1]["translation"], "")


class CoordinatorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = open_live_session(
            Path(self.temporary.name), LiveSettings(record_session=False), "test"
        )
        self.shared = settings_module.UserSettings(
            api_key="test-key", minimum_interval_seconds=0
        )

    def test_capture_failure_runs_full_cleanup_and_persists_end_state(self):
        events = []
        bus = ev.EventBus()
        bus.subscribe(events.append)

        class FakeAsr:
            instances = []

            def __init__(self, *_args, on_partial, on_final, on_error, **_kwargs):
                self.on_partial = on_partial
                self.on_final = on_final
                self.on_error = on_error
                self.stopped = False
                self.instances.append(self)

            def start(self):
                pass

            def send(self, _pcm):
                pass

            def stop(self):
                self.stopped = True

        class FakeCapture:
            instances = []

            def __init__(self, *_args, on_block, on_error, **_kwargs):
                self.on_block = on_block
                self.on_error = on_error
                self.stopped = False
                self.instances.append(self)

            def start(self):
                pass

            def stop(self):
                self.stopped = True

        class FakeTranslator:
            def __init__(self, *_args, **_kwargs):
                pass

            def chat_completions_stream(self, payload, *, on_update, **_kwargs):
                on_update("是")
                return ApiResult("qwen-mt-test", "是", 0.01, {}, None, "stop")

        with (
            mock.patch("rinayaki.live.coordinator.QwenStreamingAsr", FakeAsr),
            mock.patch("rinayaki.live.coordinator.WasapiLoopbackCapture", FakeCapture),
            mock.patch("rinayaki.live.coordinator.translation.DashScopeOpenAIClient", FakeTranslator),
        ):
            coordinator = RealtimeCoordinator(
                LiveSettings(record_session=False), self.shared, self.paths, bus=bus
            )
            coordinator.start()
            FakeAsr.instances[0].on_final("はい", 0, 500)
            deadline = time.monotonic() + 2
            while coordinator.stats["translations"] != 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            FakeCapture.instances[0].on_error("device lost")
            self.assertTrue(coordinator.wait_until_stopped(2))

        self.assertTrue(FakeCapture.instances[0].stopped)
        self.assertTrue(FakeAsr.instances[0].stopped)
        self.assertTrue(self.paths.transcript_txt.is_file())
        record = json.loads(self.paths.session_json.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "ended")
        self.assertEqual(record["ended_reason"], "capture-error")
        self.assertEqual(record["stats"]["translations"], 1)
        self.assertEqual(record["stats"]["translation_updates"], 1)
        kinds = [event.kind for event in events]
        self.assertLess(kinds.index(ev.KIND_TRANSLATION_PARTIAL), kinds.index(ev.KIND_TRANSLATION))
        self.assertEqual(events[-1].kind, ev.KIND_SESSION_ENDED)

    def test_startup_failure_still_finishes_session(self):
        events = []
        bus = ev.EventBus()
        bus.subscribe(events.append)

        class BrokenAsr:
            def __init__(self, *_args, **_kwargs):
                pass

            def start(self):
                raise RuntimeError("websocket unavailable")

            def stop(self):
                pass

        with mock.patch("rinayaki.live.coordinator.QwenStreamingAsr", BrokenAsr):
            coordinator = RealtimeCoordinator(
                LiveSettings(record_session=False), self.shared, self.paths, bus=bus
            )
            with self.assertRaisesRegex(RuntimeError, "websocket"):
                coordinator.start()

        self.assertTrue(coordinator.stopped)
        kinds = [event.kind for event in events]
        self.assertIn(ev.KIND_RUNTIME_ERROR, kinds)
        self.assertEqual(kinds[-1], ev.KIND_SESSION_ENDED)
        record = json.loads(self.paths.session_json.read_text(encoding="utf-8"))
        self.assertEqual(record["ended_reason"], "startup-failed")

    def test_source_only_mode_never_constructs_or_calls_translator(self):
        events = []
        bus = ev.EventBus()
        bus.subscribe(events.append)

        class FakeAsr:
            instance = None

            def __init__(self, *_args, on_partial, on_final, on_error, **_kwargs):
                self.on_partial = on_partial
                self.on_final = on_final
                self.on_error = on_error
                FakeAsr.instance = self

            def start(self):
                pass

            def send(self, _pcm):
                pass

            def stop(self):
                pass

        class FakeCapture:
            def __init__(self, *_args, **_kwargs):
                pass

            def start(self):
                pass

            def stop(self):
                pass

        source_settings = LiveSettings(record_session=False, display_mode="source")
        paths = open_live_session(Path(self.temporary.name), source_settings, "source-only")
        with (
            mock.patch("rinayaki.live.coordinator.QwenStreamingAsr", FakeAsr),
            mock.patch("rinayaki.live.coordinator.WasapiLoopbackCapture", FakeCapture),
            mock.patch(
                "rinayaki.live.coordinator.translation.DashScopeOpenAIClient",
                side_effect=AssertionError("translator must stay disabled"),
            ),
        ):
            coordinator = RealtimeCoordinator(source_settings, self.shared, paths, bus=bus)
            coordinator.start()
            FakeAsr.instance.on_final("原文だけ", 0, 500)
            coordinator.stop("test")

        self.assertEqual(coordinator.stats["translations"], 0)
        self.assertEqual(
            json.loads(paths.session_json.read_text(encoding="utf-8"))["provenance"]["translation_model"],
            None,
        )
        self.assertIn("原文だけ", paths.transcript_txt.read_text(encoding="utf-8"))
        self.assertFalse(any(event.kind == ev.KIND_TRANSLATION for event in events))


if __name__ == "__main__":
    unittest.main()
