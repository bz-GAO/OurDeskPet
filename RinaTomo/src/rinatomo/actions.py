"""Typed helpers over Transport.call_action.

Behavior logic should use these instead of raw action strings so a future
transport swap stays transparent.
"""

from __future__ import annotations

from typing import Any

from .events import GroupMessageEvent, MessageEvent, PrivateMessageEvent
from .transport.base import Transport

OneBotMessage = str | list[dict[str, Any]]


class Actions:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def send_private_msg(self, user_id: int, message: OneBotMessage) -> Any:
        return await self._transport.call_action(
            "send_private_msg", user_id=user_id, message=message
        )

    async def send_group_msg(self, group_id: int, message: OneBotMessage) -> Any:
        return await self._transport.call_action(
            "send_group_msg", group_id=group_id, message=message
        )

    async def reply_to_message(self, event: MessageEvent, text: str) -> Any:
        """Quote the source message and identify the sender in group replies."""
        segments: list[dict[str, Any]] = []
        if event.message_id > 0:
            segments.append({"type": "reply", "data": {"id": str(event.message_id)}})
        if isinstance(event, GroupMessageEvent):
            segments.append({"type": "at", "data": {"qq": str(event.user_id)}})
            segments.append({"type": "text", "data": {"text": f" {text}"}})
            return await self.send_group_msg(event.group_id, segments)
        if isinstance(event, PrivateMessageEvent):
            segments.append({"type": "text", "data": {"text": text}})
            return await self.send_private_msg(event.user_id, segments)
        raise TypeError(f"cannot reply to {type(event).__name__}")

    async def get_login_info(self) -> Any:
        return await self._transport.call_action("get_login_info")

    async def get_status(self) -> Any:
        return await self._transport.call_action("get_status")

    async def get_group_info(self, group_id: int) -> Any:
        return await self._transport.call_action("get_group_info", group_id=group_id)

    async def get_group_member_info(self, group_id: int, user_id: int) -> Any:
        return await self._transport.call_action(
            "get_group_member_info", group_id=group_id, user_id=user_id
        )
