"""Threaded bot runtime used by the local control panel."""

from __future__ import annotations

import asyncio
import logging
import threading
import time as time_module
from collections.abc import Callable
from contextlib import suppress

from .actions import Actions
from .config import AppConfig
from .dispatcher import Dispatcher, Handler
from .events import Event, GroupMessageEvent, MessageEvent
from .handlers import make_echo, ping
log = logging.getLogger(__name__)

from .handlers.chat import ChatResponder
from .handlers.commands import CommandContext, make_commands
from .notifications import evaluate_gate, format_notification
from .config import in_night_sleep
from .permissions import Permissions
from .transport import OneBot11Transport

StatusCallback = Callable[[str, str], None]
ActivityCallback = Callable[[str], None]


def build_handlers(
    config: AppConfig,
    chat: ChatResponder,
    command_context: CommandContext | None = None,
) -> list[Handler]:
    handlers: list[Handler] = []
    if config.features.ping:
        handlers.append(ping)
    handlers.append(make_echo(config.bot.echo))
    handlers.append(chat)
    if command_context is not None:
        handlers.append(make_commands(command_context))
    return handlers


class BotService:
    def __init__(
        self,
        status_callback: StatusCallback,
        activity_callback: ActivityCallback,
    ) -> None:
        self._status_callback = status_callback
        self._activity_callback = activity_callback
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dispatcher: Dispatcher | None = None
        self._stop_event: asyncio.Event | None = None
        self._ready = threading.Event()
        self._config: AppConfig | None = None
        self._chat: ChatResponder | None = None
        self._paused = False
        self._night_sleep = False
        self._started_at: float | None = None
        self._actions: Actions | None = None
        self._command_context: CommandContext | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: AppConfig) -> None:
        if self.running:
            self.apply_behavior(config)
            return
        self._config = config
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="RinaTomoBot",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        stop_event = self._stop_event
        if loop is not None and stop_event is not None:
            with suppress(RuntimeError):  # the worker may have just closed its loop
                loop.call_soon_threadsafe(stop_event.set)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():
            # Retain ownership while cleanup is in progress; a restart must not
            # create a second live message worker after a timed-out join.
            return
        self._thread = None
        self._loop = None
        self._dispatcher = None
        self._chat = None
        self._actions = None
        self._command_context = None
        self._started_at = None

    def apply_behavior(self, config: AppConfig) -> None:
        self._config = config
        loop = self._loop
        if loop is None or self._dispatcher is None:
            return
        loop.call_soon_threadsafe(self._configure_dispatcher, config)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        loop = self._loop
        dispatcher = self._dispatcher
        if loop is not None and dispatcher is not None:
            loop.call_soon_threadsafe(self._set_runtime_enabled, not paused)

    def llm_usage(self) -> dict[str, int] | None:
        """Best-effort daily usage read from the live responder; None when stopped.

        TokenBudget serializes this cross-thread status read with reservations
        and settlements, so the three counters always describe one snapshot.
        """
        chat = self._chat
        if chat is None:
            return None
        return chat.usage_snapshot()

    def _apply_gates(self) -> None:
        """Effective service switch: pause AND night sleep both silence everything."""
        enabled = not self._paused and not self._night_sleep
        if self._dispatcher is not None:
            self._dispatcher.set_enabled(enabled)
        if self._chat is not None:
            self._chat.set_runtime_enabled(enabled)

    async def _night_watch(self) -> None:
        """Re-evaluate the night-sleep window periodically while running."""
        while True:
            await asyncio.sleep(30)
            config = self._config
            if config is None:
                continue
            state = in_night_sleep(config)
            if state != self._night_sleep:
                self._night_sleep = state
                self._activity_callback("深夜休眠开始：暂停全部服务" if state else "深夜休眠结束：恢复服务")
                self._apply_gates()

    def notify_admins(self, config: AppConfig, event: str, lines: list[str]) -> tuple[bool, str]:
        """Thread-safe push request from the control protocol; gates evaluated now."""
        reason = evaluate_gate(config, event)
        if reason is not None:
            return False, reason
        if in_night_sleep(config):
            return False, "深夜休眠中，通知已丢弃"
        loop = self._loop
        actions = self._actions
        if loop is None or actions is None or not self.running:
            return False, "bot 未运行"
        message = format_notification(
            {"translation": "翻译任务", "chat_reply": "聊天回复", "login_failure": "登录状态"}.get(event, "通知"),
            lines,
        )
        admins = list(config.permissions.admin_users)

        async def push() -> None:
            for admin in admins:
                try:
                    await actions.send_private_msg(admin, message)
                except Exception:
                    log.exception("notify push to %s failed", admin)

        loop.call_soon_threadsafe(lambda: asyncio.create_task(push()))
        return True, f"已推送给 {len(admins)} 个管理员"

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._status_callback("error", str(exc))

    async def _serve(self) -> None:
        config = self._config
        if config is None:
            return
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        transport = OneBot11Transport(config.connection)
        dispatcher = Dispatcher(
            Actions(transport),
            Permissions(config.permissions),
            self._observe_event,
        )
        self._actions = Actions(transport)
        self._dispatcher = dispatcher
        self._chat = ChatResponder(config)
        self._command_context = CommandContext(
            config_provider=lambda: self._config or config,
            usage_provider=self.llm_usage,
            started_provider=lambda: self._started_at,
        )
        self._started_at = time_module.time()
        self._configure_dispatcher(config)
        self._apply_gates()
        transport.set_event_handler(dispatcher.dispatch)
        transport.set_state_handler(self._status_callback)
        task = asyncio.create_task(transport.start())
        night_task = asyncio.create_task(self._night_watch())
        self._ready.set()
        try:
            await self._stop_event.wait()
        finally:
            try:
                await transport.stop()
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                night_task.cancel()
                with suppress(asyncio.CancelledError):
                    await night_task

    def _configure_dispatcher(self, config: AppConfig) -> None:
        if self._dispatcher is None or self._chat is None:
            return
        self._dispatcher.set_permissions(Permissions(config.permissions))
        self._chat.reconfigure(config)
        self._dispatcher.replace_handlers(
            build_handlers(config, self._chat, self._command_context)
        )

    def _set_runtime_enabled(self, enabled: bool) -> None:
        if self._dispatcher is not None:
            self._dispatcher.set_enabled(enabled)
        if self._chat is not None:
            self._chat.set_runtime_enabled(enabled)

    def _observe_event(self, event: Event, allowed: bool) -> None:
        if not isinstance(event, MessageEvent):
            return
        if isinstance(event, GroupMessageEvent):
            scope = f"群 {event.group_id}"
        else:
            scope = f"私聊 {event.user_id}"
        preview = event.text.replace("\n", " ")[:48] or "<非文本消息>"
        decision = "已放行" if allowed else "已拦截"
        self._activity_callback(f"{decision} · {scope} · {preview}")
