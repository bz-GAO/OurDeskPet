"""Event dispatch.

Handlers are async callables receiving (event, actions). All behavior logic —
now and after a RinaDesk integration — mounts here; nothing below this layer
changes when behavior grows.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from .actions import Actions
from .events import Event
from .permissions import Permissions

log = logging.getLogger(__name__)

Handler = Callable[[Event, Actions], Awaitable[None]]
EventObserver = Callable[[Event, bool], None]


class Dispatcher:
    def __init__(
        self,
        actions: Actions,
        permissions: Permissions | None = None,
        observer: EventObserver | None = None,
    ) -> None:
        self._actions = actions
        self._handlers: list[Handler] = []
        self._permissions = permissions
        self._observer = observer
        self._enabled = True

    def register(self, handler: Handler) -> Handler:
        """Decorator-style registration usable as `@dispatcher.register`."""
        self._handlers.append(handler)
        return handler

    def replace_handlers(self, handlers: list[Handler]) -> None:
        self._handlers = list(handlers)

    def set_permissions(self, permissions: Permissions) -> None:
        self._permissions = permissions

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    async def dispatch(self, event: Event) -> None:
        allowed = self._enabled and (
            self._permissions is None or self._permissions.gate(event)
        )
        if self._observer is not None:
            self._observer(event, allowed)
        if not allowed:
            return
        for handler in self._handlers:
            try:
                await handler(event, self._actions)
            except Exception:
                log.exception("handler %r failed for event %s", handler, type(event).__name__)
