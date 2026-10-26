"""Small, bounded reply-chain memory for QQ conversations."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

ConversationScope = tuple[str, int, int]
ChainKey = tuple[ConversationScope, int]


@dataclass(frozen=True)
class ChainNode:
    parent: ChainKey | None
    speaker: str
    text: str
    created: float


class ReplyChain:
    """Keeps recent parent links without mixing accounts or conversations."""

    def __init__(self) -> None:
        self._nodes: OrderedDict[ChainKey, ChainNode] = OrderedDict()

    def is_recent(
        self,
        scope: ConversationScope,
        message_id: int,
        window_seconds: float,
        *,
        now: float | None = None,
    ) -> bool:
        node = self._nodes.get((scope, message_id))
        checked_at = time.monotonic() if now is None else now
        return node is not None and checked_at - node.created <= window_seconds

    def remember(
        self,
        scope: ConversationScope,
        message_id: int,
        *,
        parent_id: int | None,
        speaker: str,
        text: str,
        store_limit: int,
        created: float | None = None,
    ) -> None:
        if message_id <= 0:
            return
        key = (scope, message_id)
        self._nodes[key] = ChainNode(
            parent=(scope, parent_id) if parent_id is not None else None,
            speaker=speaker,
            text=text,
            created=time.monotonic() if created is None else created,
        )
        self._nodes.move_to_end(key)
        while len(self._nodes) > store_limit:
            self._nodes.popitem(last=False)

    def history(
        self,
        scope: ConversationScope,
        quoted_id: int | None,
        *,
        max_depth: int,
        window_seconds: float,
        now: float | None = None,
    ) -> list[tuple[str, str]]:
        """Return one quoted parent path, oldest first.

        Every node is checked against the time window. This prevents a recent
        leaf from retaining ancestors that should already have expired.
        """
        if quoted_id is None:
            return []
        checked_at = time.monotonic() if now is None else now
        path: list[tuple[str, str]] = []
        visited: set[ChainKey] = set()
        key: ChainKey | None = (scope, quoted_id)
        while key is not None and len(path) < max_depth and key not in visited:
            visited.add(key)
            node = self._nodes.get(key)
            if node is None or checked_at - node.created > window_seconds:
                break
            path.append((node.speaker, node.text))
            key = node.parent
        path.reverse()
        return path
