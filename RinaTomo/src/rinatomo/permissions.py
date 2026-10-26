"""Permission guard: default-deny gate between transport and handlers.

Design: whitelist-only. Any message from a user/group not listed in
PermissionsConfig is dropped silently (logged for debugging, never answered).
A separate blocklist is meaningless in this mode — it only makes sense in an
allow-all-except model, which this bot deliberately is not.

Admins bypass everything. Group messages from non-admins require the group to
be whitelisted. Private messages from non-admins require the user to be in
private_whitelist. Non-message events (meta/notice/request) pass through;
handlers decide whether they care.
"""

from __future__ import annotations

import logging

from .config import PermissionsConfig
from .events import GroupMessageEvent, MessageEvent, PrivateMessageEvent

log = logging.getLogger(__name__)


class Permissions:
    def __init__(self, config: PermissionsConfig) -> None:
        self._admin_users = frozenset(config.admin_users)
        self._private_whitelist = frozenset(config.private_whitelist)
        self._enabled_groups = frozenset(config.enabled_groups)

    def allows(self, event: object) -> bool:
        if not isinstance(event, MessageEvent):
            return True
        if event.user_id in self._admin_users:
            return True
        if isinstance(event, PrivateMessageEvent):
            return event.user_id in self._private_whitelist
        if isinstance(event, GroupMessageEvent):
            return event.group_id in self._enabled_groups
        return False

    def gate(self, event: object) -> bool:
        """Check + log denials; True means the event may be dispatched."""
        if self.allows(event):
            return True
        if isinstance(event, MessageEvent):
            scope = (
                f"group {event.group_id}" if isinstance(event, GroupMessageEvent) else "private"
            )
            log.info("permission denied: %s from user %s ignored", scope, event.user_id)
        return False
