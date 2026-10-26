"""Local control protocol shared by the standalone panel and RinaDesk."""
from __future__ import annotations
import json
import math
import queue
import socket
import threading
import time
from dataclasses import dataclass, replace

from .config import AppConfig, ConfigError, _parse_clock
from .napcat import NapCatSettings

CONTROL_ADDRESS = ("127.0.0.1", 37642)
CONTROL_COMMAND = b"RINATOMO_SHOW\n"
MAX_REQUEST_BYTES = 65_536


@dataclass
class ControlRequest:
    command: str
    payload: dict[str, object]
    response: queue.Queue


def request_existing_panel() -> bool:
    try:
        with socket.create_connection(CONTROL_ADDRESS, timeout=0.6) as connection:
            connection.sendall(CONTROL_COMMAND)
            return connection.recv(16) == b"OK\n"
    except OSError:
        return False


class PanelControlServer:
    def __init__(self, events: queue.Queue, address=CONTROL_ADDRESS) -> None:
        self.events = events
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            self.socket.bind(address)
            self.socket.listen(4)
            self.socket.settimeout(0.5)
        except OSError:
            self.socket.close()
            raise
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._serve, name="RinaTomoPanelControl", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _read_request(self, connection: socket.socket) -> bytes:
        deadline = time.monotonic() + 1.0
        chunks = bytearray()
        # JSON clients half-close the write side; the legacy show command ends in LF.
        while len(chunks) <= MAX_REQUEST_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Tomo request read timed out")
            connection.settimeout(remaining)
            part = connection.recv(min(4096, MAX_REQUEST_BYTES + 1 - len(chunks)))
            if not part:
                break
            chunks.extend(part)
            if chunks == CONTROL_COMMAND:
                break
        if len(chunks) > MAX_REQUEST_BYTES:
            raise ValueError("Tomo 控制请求过长")
        return bytes(chunks)

    def _serve(self) -> None:
        while not self.stopped.is_set():
            try:
                connection, _ = self.socket.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with connection:
                try:
                    command = self._read_request(connection)
                    if command == CONTROL_COMMAND:
                        self.events.put(("show_window", None))
                        connection.sendall(b"OK\n")
                        continue
                    data = json.loads(command.decode("utf-8"))
                    if not isinstance(data, dict) or type(data.get("protocolVersion")) is not int or data["protocolVersion"] != 1:
                        raise ValueError("不支持的 Tomo 协议版本")
                    payload = data.get("payload", {})
                    if not isinstance(payload, dict):
                        raise ValueError("payload 必须是对象")
                    response: queue.Queue = queue.Queue(maxsize=1)
                    self.events.put(("control_request", ControlRequest(str(data.get("command", "")), payload, response)))
                    result = response.get(timeout=5.0)
                except (ValueError, queue.Empty) as exc:
                    result = {"ok": False, "error": str(exc) or "Tomo 控制请求超时"}
                except OSError:
                    continue
                try:
                    connection.sendall((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
                except OSError:
                    pass

    def stop(self) -> None:
        self.stopped.set()
        self.socket.close()


def prepare_update(config: AppConfig, settings: NapCatSettings, payload: dict):
    """Validate one settings group before changing disk, runtime or either UI."""
    groups = {"features", "llm", "permissions", "autoStart", "notifications"}
    if len(payload) != 1 or not set(payload) <= groups:
        raise ConfigError("每次只应用一个设置分组：features、llm、permissions 或 autoStart")
    group = next(iter(payload))
    value = payload[group]
    if group == "autoStart":
        if not isinstance(value, bool):
            raise ConfigError("autoStart 必须是布尔值")
        return config, replace(settings, auto_start=value)
    if not isinstance(value, dict):
        raise ConfigError(f"{group} 必须是对象")
    if group == "features":
        if not set(value) <= {"ping", "echo"}:
            raise ConfigError("未知的功能设置；请确认两端已更新到相同版本")
        ping = value.get("ping", config.features.ping)
        echo = value.get("echo", config.bot.echo)
        if not all(isinstance(item, bool) for item in (ping, echo)):
            raise ConfigError("功能开关必须是布尔值")
        return replace(config, features=replace(config.features, ping=ping), bot=replace(config.bot, echo=echo)), settings
    if group == "llm":
        names = {
            "enabled": "enabled",
            "minReplyInterval": "min_reply_interval",
            "timeoutSeconds": "timeout_seconds",
            "maxTokens": "max_tokens",
            "dailyTokenBudget": "daily_token_budget",
            "maxInputChars": "max_input_chars",
            "maxConcurrentRequests": "max_concurrent_requests",
        }
        if not set(value) <= names.keys():
            raise ConfigError("未知的大模型服务设置")
        changes = {}
        for key, item in value.items():
            if key == "enabled":
                if not isinstance(item, bool):
                    raise ConfigError("大模型服务开关必须是布尔值")
            elif key in {"minReplyInterval", "timeoutSeconds"}:
                if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                    raise ConfigError(f"{key} 必须是有限数字")
                if item < 0 or (key == "timeoutSeconds" and item == 0):
                    raise ConfigError(f"{key} 超出允许范围")
                item = float(item)
            elif isinstance(item, bool) or not isinstance(item, int) or item < 1:
                raise ConfigError(f"{key} 必须是大于零的整数")
            changes[names[key]] = item
        return replace(config, llm=replace(config.llm, **changes)), settings
    if group == "notifications":
        names = {"enabled", "nightSleepEnabled", "nightStart", "nightEnd", "events"}
        if not set(value) <= names:
            raise ConfigError("未知的通知设置")
        events = value.get("events", {})
        if not isinstance(events, dict) or not set(events) <= {"translation", "chatReply", "loginFailure"}:
            raise ConfigError("未知的通知事件设置")
        for key, item in value.items():
            if key in {"enabled", "nightSleepEnabled"} and not isinstance(item, bool):
                raise ConfigError(f"{key} 必须是布尔值")
        night_start = _parse_clock(value.get("nightStart", config.notifications.night_start), "nightStart")
        night_end = _parse_clock(value.get("nightEnd", config.notifications.night_end), "nightEnd")
        if night_start == night_end:
            raise ConfigError("nightStart 与 nightEnd 不能相同")
        event_names = {"translation": "translation", "chatReply": "chat_reply", "loginFailure": "login_failure"}
        event_changes = {event_names[key]: item for key, item in events.items()}
        for item in event_changes.values():
            if not isinstance(item, bool):
                raise ConfigError("通知事件开关必须是布尔值")
        notifications = replace(
            config.notifications,
            enabled=value.get("enabled", config.notifications.enabled),
            night_sleep_enabled=value.get("nightSleepEnabled", config.notifications.night_sleep_enabled),
            night_start=night_start.strftime("%H:%M"),
            night_end=night_end.strftime("%H:%M"),
            events=replace(config.notifications.events, **event_changes),
        )
        if not isinstance(notifications.enabled, bool) or not isinstance(notifications.night_sleep_enabled, bool):
            raise ConfigError("通知开关必须是布尔值")
        return replace(config, notifications=notifications), settings
    names = {"adminUsers": "admin_users", "privateWhitelist": "private_whitelist", "enabledGroups": "enabled_groups"}
    if not set(value) <= names.keys():
        raise ConfigError("未知的权限设置")
    changes = {}
    for key, values in value.items():
        if not isinstance(values, list) or any(type(item) is not int or not 0 < item <= 9_007_199_254_740_991 for item in values):
            raise ConfigError(f"{key} 必须是有效的正整数 QQ/群号列表")
        changes[names[key]] = list(dict.fromkeys(values))
    return replace(config, permissions=replace(config.permissions, **changes)), settings
