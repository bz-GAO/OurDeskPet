"""OneBot 11 WebSocket client transport.

Connects out to a NapCat/LLOneBot-style endpoint, consumes events, and issues
actions with echo-id correlation. Reconnects with a fixed delay; heartbeat
messages are tolerated but not enforced in the skeleton.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import aiohttp

from ..config import ConnectionConfig
from ..events import Event, parse_event
from .base import EventHandler, StateHandler, Transport, TransportError

log = logging.getLogger(__name__)

ACTION_TIMEOUT = 15.0


class OneBot11Transport(Transport):
    def __init__(self, connection: ConnectionConfig) -> None:
        self._connection = connection
        self._handler: EventHandler | None = None
        self._state_handler: StateHandler | None = None
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._event_tasks: set[asyncio.Task[None]] = set()
        self._stop_requested = False

    def set_event_handler(self, handler: EventHandler) -> None:
        self._handler = handler

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    async def start(self) -> None:
        self._stop_requested = False
        backoff = self._connection.reconnect_delay
        while not self._stop_requested:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("connection to %s failed: %s", self._connection.url, exc)
                self._notify_state("waiting", str(exc))
            if self._stop_requested:
                break
            log.info("reconnecting in %.1fs", backoff)
            await asyncio.sleep(backoff)

    async def stop(self) -> None:
        self._stop_requested = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._fail_pending("transport stopped")
        tasks = tuple(self._event_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._notify_state("stopped", "")

    async def call_action(self, action: str, **params: Any) -> Any:
        if self._ws is None or self._ws.closed:
            raise TransportError("not connected")
        echo = uuid.uuid4().hex
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        try:
            await self._ws.send_json({"action": action, "params": params, "echo": echo})
            response = await asyncio.wait_for(future, timeout=ACTION_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise TransportError(f"action {action!r} timed out") from exc
        except TransportError:
            raise
        except (aiohttp.ClientError, ConnectionError, RuntimeError) as exc:
            raise TransportError(f"action {action!r} could not be sent: {exc}") from exc
        finally:
            self._pending.pop(echo, None)
        if response.get("retcode") != 0:
            raise TransportError(
                f"action {action!r} failed: retcode={response.get('retcode')} "
                f"status={response.get('status')} wording={response.get('wording', '')}"
            )
        return response.get("data")

    async def _run_once(self) -> None:
        headers = {}
        if self._connection.access_token:
            headers["Authorization"] = f"Bearer {self._connection.access_token}"
        self._session = aiohttp.ClientSession()
        try:
            log.info("connecting to %s", self._connection.url)
            self._notify_state("connecting", self._connection.url)
            self._ws = await self._session.ws_connect(self._connection.url, headers=headers)
            log.info("connected")
            self._notify_state("connected", self._connection.url)
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                    except (json.JSONDecodeError, TypeError):
                        log.warning("ignoring malformed JSON payload")
                        continue
                    if not isinstance(payload, dict):
                        log.warning("ignoring non-object JSON payload")
                        continue
                    await self._handle_payload(payload)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
            log.info("connection closed by endpoint")
        finally:
            self._fail_pending("connection closed")
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._session = None
            self._ws = None
            if not self._stop_requested:
                self._notify_state("disconnected", "connection closed")

    async def _handle_payload(self, payload: dict[str, Any]) -> None:
        echo = payload.get("echo")
        if echo is not None and echo in self._pending:
            future = self._pending.pop(echo)
            if not future.done():
                future.set_result(payload)
            return
        event = parse_event(payload)
        if event is None:
            log.debug("unhandled payload: %s", payload)
            return
        if self._handler is not None:
            # Fire-and-forget: awaiting the handler here would block the recv
            # loop, and actions issued from a handler await echo responses
            # that only this same loop can deliver — a guaranteed deadlock.
            task = asyncio.create_task(self._handler(event))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_task_done)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(TransportError(reason))
        self._pending.clear()

    def _event_task_done(self, task: asyncio.Task[None]) -> None:
        self._event_tasks.discard(task)
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            log.error(
                "event handler failed",
                exc_info=(type(exception), exception, exception.__traceback__),
            )

    def _notify_state(self, state: str, detail: str) -> None:
        if self._state_handler is None:
            return
        try:
            self._state_handler(state, detail)
        except Exception:
            log.exception("transport state handler failed")
