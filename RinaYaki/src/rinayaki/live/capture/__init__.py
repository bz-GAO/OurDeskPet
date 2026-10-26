"""Audio capture backends for the live runtime.

``WasapiLoopbackCapture`` covers system-audio sources in the first version
(browser, players, most live streams). The ``CaptureSource`` protocol keeps
the door open for direct stream capture (YouTube/Bilibili live URLs) later
without changing the coordinator's contract.
"""
from __future__ import annotations

from typing import Callable, Protocol


class CaptureSource(Protocol):
    name: str

    def start(self, on_block: Callable[[bytes], None], on_error: Callable[[str], None]) -> None: ...

    def stop(self) -> None: ...


class CaptureError(RuntimeError):
    pass


def list_loopback_devices() -> list[dict]:
    from .wasapi_loopback import list_loopback_devices as _list

    return _list()
