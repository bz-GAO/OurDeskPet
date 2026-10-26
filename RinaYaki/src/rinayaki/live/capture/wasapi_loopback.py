"""WASAPI loopback capture of system audio on Windows.

Records what the selected output device is playing (browser, media player,
live streams) and converts it to the 16 kHz mono int16 stream consumed by
the realtime ASR and the session recorder. The ``soundcard`` package is
loaded lazily so the rest of the live runtime works without audio support.
"""
from __future__ import annotations

from collections.abc import Callable
import threading

import numpy as np

from . import CaptureError


OUTPUT_SAMPLE_RATE = 16_000


def _soundcard():
    try:
        import soundcard
    except ImportError as error:
        raise CaptureError(
            "缺少 soundcard 音频库；请在 RinaYaki 虚拟环境中运行 "
            "`python -m pip install soundcard` 后重试。"
        ) from error
    return soundcard


def list_loopback_devices() -> list[dict]:
    sc = _soundcard()
    devices = []
    for microphone in sc.all_microphones(include_loopback=True):
        if not microphone.isloopback:
            continue
        devices.append({
            "id": microphone.id,
            "name": microphone.name,
            "is_loopback": bool(microphone.isloopback),
            "channels": microphone.channels,
        })
    return devices


def _default_loopback_id() -> str:
    """Follow the system default output device, falling back to any loopback."""
    sc = _soundcard()
    loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    if not loopbacks:
        raise CaptureError("没有找到可用的系统声音（WASAPI loopback）设备。")
    try:
        default_id = sc.default_speaker().id
    except Exception:
        default_id = None
    if default_id:
        for microphone in loopbacks:
            if microphone.id == default_id:
                return microphone.id
    return loopbacks[0].id


def _resolve_device(device: str | None):
    sc = _soundcard()
    if device:
        for microphone in sc.all_microphones(include_loopback=True):
            if microphone.isloopback and (
                microphone.id == device or device.casefold() in microphone.name.casefold()
            ):
                return microphone
        raise CaptureError(f"找不到系统声音 loopback 设备：{device}")
    return sc.get_microphone(_default_loopback_id(), include_loopback=True)


def _to_16k_mono_int16(frames: np.ndarray, native_rate: int) -> bytes:
    if native_rate <= 0:
        raise ValueError("native_rate must be positive")
    if frames.size == 0:
        return b""
    mono = frames.mean(axis=1) if frames.ndim > 1 else frames
    if native_rate != OUTPUT_SAMPLE_RATE:
        count = int(len(mono) * OUTPUT_SAMPLE_RATE / native_rate)
        positions = np.linspace(0, len(mono) - 1, num=max(1, count))
        mono = np.interp(positions, np.arange(len(mono)), mono)
    np.clip(mono, -1.0, 1.0, out=mono)
    return (mono * 32_767).astype("<i2").tobytes()


class WasapiLoopbackCapture:
    """System-audio capture via WASAPI loopback; non-blocking push consumer."""

    name = "wasapi_loopback"

    def __init__(
        self,
        device: str | None = None,
        *,
        frame_ms: int = 200,
        on_block: Callable[[bytes], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._device = device
        self._frame_ms = frame_ms
        self._on_block = on_block
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            raise CaptureError("采集已经启动。")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="yaki-live-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        sc = _soundcard()
        try:
            microphone = _resolve_device(self._device)
            # WASAPI loopback is delivered in the device's shared-mode mix rate;
            # record at that rate and downsample ourselves for stable results.
            with microphone.recorder(samplerate=48_000, channels=2) as recorder:
                frame_samples = int(48_000 * self._frame_ms / 1000)
                while not self._stop_event.is_set():
                    frames = recorder.record(numframes=frame_samples)
                    if len(frames) == 0:
                        continue
                    self._on_block(_to_16k_mono_int16(frames, 48_000))
        except CaptureError as error:
            self._on_error(str(error))
        except Exception as error:
            self._on_error(f"系统声音采集失败：{error}")
