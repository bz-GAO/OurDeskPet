"""Normalized event model.

OneBot 11 payloads are parsed here so handlers and any future RinaDesk
integration never depend on protocol details. New transports only need to
produce these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """Base event; keeps the raw payload for anything not yet modeled."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def time(self) -> float:
        try:
            return float(self.raw.get("time", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @property
    def self_id(self) -> int | None:
        value = self.raw.get("self_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None


@dataclass
class MessageEvent(Event):
    user_id: int = 0
    message_id: int = 0
    text: str = ""

    @property
    def exact_text(self) -> str:
        """Plain text exactly as sent: no trim, no case folding.

        Use for case- and whitespace-sensitive command matching.
        """
        message = self.raw.get("message")
        if isinstance(message, list):
            # A strict text trigger must not match a message that also carries
            # an @ mention, image, reply, or any other non-text segment.
            if not all(isinstance(seg, dict) and seg.get("type") == "text" for seg in message):
                return ""
            return "".join(str(seg.get("data", {}).get("text", "")) for seg in message)
        if isinstance(message, str):
            return message
        return str(self.raw.get("raw_message", ""))

    @property
    def is_at_me(self) -> bool:
        segments = self.raw.get("message")
        if isinstance(segments, list):
            return any(
                seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == str(self.self_id)
                for seg in segments
                if isinstance(seg, dict)
            )
        return False


@dataclass
class PrivateMessageEvent(MessageEvent):
    pass


@dataclass
class GroupMessageEvent(MessageEvent):
    group_id: int = 0


@dataclass
class MetaEvent(Event):
    meta_type: str = ""  # "heartbeat" | "lifecycle" | ...


@dataclass
class NoticeEvent(Event):
    notice_type: str = ""


@dataclass
class RequestEvent(Event):
    request_type: str = ""


def parse_event(payload: dict[str, Any]) -> Event | None:
    """Build a normalized event from an OneBot 11 event JSON object.

    Returns None for payloads that are not events (e.g. action responses).
    """
    post_type = payload.get("post_type")
    if post_type == "message":
        base_kwargs = {
            "raw": payload,
            "user_id": _as_int(payload.get("user_id")),
            "message_id": _as_int(payload.get("message_id")),
            "text": extract_plain_text(payload),
        }
        message_type = payload.get("message_type")
        if message_type == "group":
            return GroupMessageEvent(group_id=_as_int(payload.get("group_id")), **base_kwargs)
        if message_type == "private":
            return PrivateMessageEvent(**base_kwargs)
        return None
    if post_type == "meta_event":
        return MetaEvent(raw=payload, meta_type=str(payload.get("meta_event_type", "")))
    if post_type == "notice":
        return NoticeEvent(raw=payload, notice_type=str(payload.get("notice_type", "")))
    if post_type == "request":
        return RequestEvent(raw=payload, request_type=str(payload.get("request_type", "")))
    return None


def extract_plain_text(payload: dict[str, Any]) -> str:
    """Best-effort plain text from the message field.

    Handles both the segment array form and the CQ-code string form; CQ codes
    are kept as-is in the string form since the skeleton only needs text.
    """
    message = payload.get("message")
    if isinstance(message, list):
        parts = [
            str(seg.get("data", {}).get("text", ""))
            for seg in message
            if isinstance(seg, dict) and seg.get("type") == "text"
        ]
        return "".join(parts).strip()
    if isinstance(message, str):
        return message.strip()
    return str(payload.get("raw_message", "")).strip()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
