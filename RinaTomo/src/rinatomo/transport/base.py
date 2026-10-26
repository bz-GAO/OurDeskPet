"""Transport abstraction.

The only contract the upper layers (dispatcher, handlers, future RinaDesk
integration) see. Swapping the access method — e.g. to the official QQ bot
API — means adding a new Transport implementation, nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from ..events import Event

EventHandler = Callable[[Event], Awaitable[None]]
StateHandler = Callable[[str, str], None]


class Transport(ABC):
    """Bidirectional channel to a QQ protocol endpoint."""

    @abstractmethod
    def set_event_handler(self, handler: EventHandler) -> None:
        """Register the async callback invoked for every normalized event."""

    @abstractmethod
    async def start(self) -> None:
        """Start receiving events. Long-running; returns on shutdown."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop receiving and release resources."""

    @abstractmethod
    async def call_action(self, action: str, **params: Any) -> Any:
        """Invoke a protocol capability and return its `data` payload.

        Raises TransportError on failure or timeout.
        """


class TransportError(RuntimeError):
    pass
