"""Connectivity-verification handlers.

These deliberately small handlers prove the receive/send loop works. Product
behavior should live in its own handler module rather than growing this file.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..actions import Actions
from ..events import Event, GroupMessageEvent, MessageEvent, PrivateMessageEvent

Handler = Callable[[Event, Actions], Awaitable[None]]


async def ping(event: Event, actions: Actions) -> None:
    """Reply 'pong' to 'ping' so a live link is easy to confirm by hand."""
    if not isinstance(event, MessageEvent) or event.text.lower() not in ("ping", "/ping"):
        return
    if isinstance(event, GroupMessageEvent):
        await actions.send_group_msg(event.group_id, "pong")
    elif isinstance(event, PrivateMessageEvent):
        await actions.send_private_msg(event.user_id, "pong")


def make_echo(enabled: bool) -> Handler:
    """Create the optional commissioning-only parrot handler."""

    async def echo(event: Event, actions: Actions) -> None:
        if not enabled or not isinstance(event, MessageEvent) or not event.text:
            return
        if isinstance(event, GroupMessageEvent):
            await actions.send_group_msg(event.group_id, event.text)
        elif isinstance(event, PrivateMessageEvent):
            await actions.send_private_msg(event.user_id, event.text)

    return echo
