"""A minimal fake OneBot 11 endpoint for tests and offline commissioning.

Speaks just enough of the protocol: accepts WebSocket connections, echoes a
successful action response for every action received, and can push a canned
group message event via `push_group_message`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import WSMsgType, web


class FakeOneBotServer:
    def __init__(
        self,
        access_token: str | None = None,
        *,
        respond_to_actions: bool = True,
    ) -> None:
        self.access_token = access_token
        self.respond_to_actions = respond_to_actions
        self.received_actions: list[dict[str, Any]] = []
        self.runner: web.AppRunner | None = None
        self._clients: list[web.WebSocketResponse] = []

    async def start(self) -> str:
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = self.runner.addresses[0][1]
        return f"ws://127.0.0.1:{port}/ws"

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    @property
    def connected(self) -> bool:
        return bool(self._clients)

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        if self.access_token is not None:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self.access_token}":
                raise web.HTTPUnauthorized()
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.append(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    break
                payload = json.loads(msg.data)
                self.received_actions.append(payload)
                if not self.respond_to_actions:
                    await ws.close()
                    break
                await ws.send_json(
                    {"status": "ok", "retcode": 0, "data": {"message_id": 1}, "echo": payload.get("echo")}
                )
        finally:
            self._clients.remove(ws)
        return ws

    async def push_group_message(self, text: str, group_id: int = 10086, user_id: int = 1234) -> None:
        event = {
            "post_type": "message",
            "message_type": "group",
            "time": 0,
            "self_id": 999,
            "group_id": group_id,
            "user_id": user_id,
            "message_id": 42,
            "message": [{"type": "text", "data": {"text": text}}],
            "raw_message": text,
        }
        for ws in list(self._clients):
            await ws.send_str(json.dumps(event))


async def wait_for_condition(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met before timeout")
