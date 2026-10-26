"""Configuration loading.

Real settings live in %LOCALAPPDATA%\\RinaTomo\\config.toml and never in the
repository. The schema here is the stable contract a future RinaDesk control
panel would read/write.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

APP_DIR_NAME = "RinaTomo"
CONFIG_FILE_NAME = "config.toml"


class ConfigError(ValueError):
    """Raised when a configuration file has an invalid value or shape."""


def default_config_dir() -> Path:
    override = os.environ.get("RINATOMO_CONFIG_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "OurDeskPet" / APP_DIR_NAME
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "rinatomo"


def default_config_path() -> Path:
    return default_config_dir() / CONFIG_FILE_NAME


@dataclass
class ConnectionConfig:
    url: str = "ws://127.0.0.1:3002"
    access_token: str = ""
    reconnect_delay: float = 3.0


@dataclass
class BotConfig:
    name: str = "rinatomo"
    echo: bool = False


@dataclass
class FeaturesConfig:
    ping: bool = True


@dataclass
class PermissionsConfig:
    """Default-deny: anyone not listed here gets silence, never a reply."""

    admin_users: list[int] = field(default_factory=list)
    private_whitelist: list[int] = field(default_factory=list)  # non-admin private chat
    enabled_groups: list[int] = field(default_factory=list)  # any member may trigger


@dataclass
class LlmConfig:
    """Text LLM responder. Credentials never live in this structure."""

    enabled: bool = False
    model: str = "qwen-turbo"
    timeout_seconds: float = 30.0
    max_tokens: int = 512
    daily_token_budget: int = 200000
    min_reply_interval: float = 0.0
    max_input_chars: int = 2000
    max_concurrent_requests: int = 2


@dataclass
class NotificationEvents:
    """Which '错过的事项' may be pushed to admin users."""

    translation: bool = True
    chat_reply: bool = False
    login_failure: bool = True


@dataclass
class NotificationsConfig:
    """Proactive push to admin users only. Night sleep silences everything."""

    enabled: bool = True
    night_sleep_enabled: bool = True
    night_start: str = "22:00"
    night_end: str = "08:00"
    events: NotificationEvents = field(default_factory=NotificationEvents)


@dataclass
class CommandsConfig:
    """# 命令别名：键需以 # 开头；值是内置命令名（yaki_state/tomo_state/help）
    或一段固定回复文本。"""

    aliases: dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    commands: CommandsConfig = field(default_factory=CommandsConfig)
    path: Path | None = None

    def sanitized_summary(self) -> str:
        """Human-readable summary safe to print: never includes the token."""
        token_state = "set" if self.connection.access_token else "empty"
        if self.path is None:
            path_summary = "<built-in defaults>"
        elif self.path.is_file():
            path_summary = str(self.path)
        else:
            path_summary = f"{self.path} (not found; using defaults)"
        return (
            f"config file: {path_summary}\n"
            f"connection.url: {self.connection.url}\n"
            f"connection.access_token: {token_state}\n"
            f"connection.reconnect_delay: {self.connection.reconnect_delay}\n"
            f"bot.name: {self.bot.name}\n"
            f"bot.echo: {self.bot.echo}\n"
            f"features.ping: {self.features.ping}\n"
            f"permissions.admin_users: {self.permissions.admin_users}\n"
            f"permissions.private_whitelist: {self.permissions.private_whitelist}\n"
            f"permissions.enabled_groups: {self.permissions.enabled_groups}\n"
            f"llm.enabled: {self.llm.enabled}\n"
            f"llm.model: {self.llm.model}\n"
            f"llm.min_reply_interval: {self.llm.min_reply_interval}\n"
            f"llm.daily_token_budget: {self.llm.daily_token_budget}"
        )


def load(path: str | Path | None = None) -> AppConfig:
    """Load config from an explicit path, the default user path, or defaults."""
    if path is not None:
        candidate = Path(path).expanduser().resolve(strict=False)
    else:
        candidate = default_config_path().resolve(strict=False)

    if candidate.is_file():
        return _from_file(candidate)
    if path is not None:
        raise FileNotFoundError(f"config file not found: {candidate}")

    log.info("no config file found at %s; using built-in defaults", candidate)
    # Keep the effective save path even before the first configuration is written.
    return AppConfig(path=candidate)


def _from_file(path: Path) -> AppConfig:
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    connection_raw = _table(raw, "connection")
    bot_raw = _table(raw, "bot")
    features_raw = _table(raw, "features")
    permissions_raw = _table(raw, "permissions")
    llm_raw = _table(raw, "llm")
    notifications_raw = _table(raw, "notifications")
    commands_raw = _table(raw, "commands")

    url = _string(connection_raw, "url", ConnectionConfig.url).strip()
    _validate_websocket_url(url)

    reconnect_delay = _number(connection_raw, "reconnect_delay", 3.0)
    if not math.isfinite(reconnect_delay) or reconnect_delay <= 0:
        raise ConfigError("connection.reconnect_delay must be a finite number greater than zero")

    return AppConfig(
        connection=ConnectionConfig(
            url=url,
            access_token=_string(connection_raw, "access_token", ""),
            reconnect_delay=reconnect_delay,
        ),
        bot=BotConfig(
            name=_non_empty_string(bot_raw, "name", "rinatomo"),
            echo=_boolean(bot_raw, "echo", False),
        ),
        features=FeaturesConfig(
            ping=_boolean(features_raw, "ping", True),
        ),
        permissions=PermissionsConfig(
            admin_users=_id_list(permissions_raw, "admin_users"),
            private_whitelist=_id_list(permissions_raw, "private_whitelist"),
            enabled_groups=_id_list(permissions_raw, "enabled_groups"),
        ),
        llm=_llm_from_table(llm_raw),
        notifications=_notifications_from_table(notifications_raw),
        commands=_commands_from_table(commands_raw),
        path=path,
    )


def _llm_from_table(section: dict[str, Any]) -> LlmConfig:
    config = LlmConfig(
        enabled=_boolean(section, "enabled", False),
        model=_non_empty_string(section, "model", LlmConfig.model),
        timeout_seconds=_number(section, "timeout_seconds", LlmConfig.timeout_seconds),
        max_tokens=section.get("max_tokens", LlmConfig.max_tokens),
        daily_token_budget=section.get("daily_token_budget", LlmConfig.daily_token_budget),
        min_reply_interval=_number(
            section, "min_reply_interval", LlmConfig.min_reply_interval
        ),
        max_input_chars=section.get("max_input_chars", LlmConfig.max_input_chars),
        max_concurrent_requests=section.get(
            "max_concurrent_requests", LlmConfig.max_concurrent_requests
        ),
    )
    if not math.isfinite(config.timeout_seconds) or config.timeout_seconds <= 0:
        raise ConfigError("llm.timeout_seconds must be a finite number greater than zero")
    if not math.isfinite(config.min_reply_interval) or config.min_reply_interval < 0:
        raise ConfigError("llm.min_reply_interval must be a finite number greater than or equal to zero")
    positive_integers = (
        ("llm.max_tokens", config.max_tokens),
        ("llm.daily_token_budget", config.daily_token_budget),
        ("llm.max_input_chars", config.max_input_chars),
        ("llm.max_concurrent_requests", config.max_concurrent_requests),
    )
    for name, value in positive_integers:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"{name} must be an integer greater than zero")
    return config


def _parse_clock(value: object, name: str) -> dt.time:
    """Validate an 'HH:MM' 24-hour clock string; returns the parsed time."""
    if not isinstance(value, str):
        raise ConfigError(f"{name} 必须是 'HH:MM' 格式的时间字符串")
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() and len(part) == 2 for part in parts):
        raise ConfigError(f"{name} 必须是 'HH:MM' 格式的时间字符串")
    hour, minute = int(parts[0]), int(parts[1])
    if hour > 23 or minute > 59:
        raise ConfigError(f"{name} 超出 24 小时制范围")
    return dt.time(hour, minute)


def _notifications_from_table(section: dict[str, Any]) -> NotificationsConfig:
    config = NotificationsConfig(
        enabled=_boolean(section, "enabled", True),
        night_sleep_enabled=_boolean(section, "night_sleep_enabled", True),
        night_start=_parse_clock(section.get("night_start", "22:00"), "notifications.night_start").strftime("%H:%M"),
        night_end=_parse_clock(section.get("night_end", "08:00"), "notifications.night_end").strftime("%H:%M"),
        events=NotificationEvents(
            translation=_boolean(section.get("events", {}), "translation", True),
            chat_reply=_boolean(section.get("events", {}), "chat_reply", False),
            login_failure=_boolean(section.get("events", {}), "login_failure", True),
        ),
    )
    events_raw = section.get("events", {})
    if not isinstance(events_raw, dict) or not set(events_raw) <= {"translation", "chat_reply", "login_failure"}:
        raise ConfigError("未知的通知事件设置")
    return config


def _commands_from_table(section: dict[str, Any]) -> CommandsConfig:
    aliases_raw = section.get("aliases", {})
    if not isinstance(aliases_raw, dict):
        raise ConfigError("commands.aliases 必须是表")
    aliases: dict[str, str] = {}
    for key, value in aliases_raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError("commands.aliases 的键值都必须是字符串")
        normalized = "#" + key.strip().lstrip("#").lower()
        if len(normalized) < 2 or len(normalized) > 32:
            raise ConfigError(f"commands.aliases 键 {normalized!r} 长度需为 1-31 个字符")
        if not value.strip() or len(value) > 200:
            raise ConfigError(f"commands.aliases 的 {normalized!r} 值需为 1-200 字符")
        aliases[normalized] = value.strip()
    return CommandsConfig(aliases=aliases)


def in_night_sleep(config: AppConfig, now: dt.datetime | None = None) -> bool:
    """Whether the bot is inside its night-sleep window (fully silent)."""
    notifications = config.notifications
    if not notifications.night_sleep_enabled:
        return False
    start = _parse_clock(notifications.night_start, "notifications.night_start")
    end = _parse_clock(notifications.night_end, "notifications.night_end")
    if start == end:
        return False
    current = (now or dt.datetime.now()).time().replace(second=0, microsecond=0)
    start_minutes, end_minutes = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    minutes = current.hour * 60 + current.minute
    if start_minutes < end_minutes:
        return start_minutes <= minutes < end_minutes
    return minutes >= start_minutes or minutes < end_minutes


def save(config: AppConfig, path: str | Path | None = None) -> Path:
    """Validate and atomically persist the user-editable configuration."""
    target = Path(path or config.path or default_config_path()).expanduser().resolve(strict=False)
    if config.connection.reconnect_delay <= 0 or not math.isfinite(config.connection.reconnect_delay):
        raise ConfigError("connection.reconnect_delay must be a finite number greater than zero")
    _validate_websocket_url(config.connection.url)
    _llm_from_table({
        "enabled": config.llm.enabled,
        "model": config.llm.model,
        "timeout_seconds": config.llm.timeout_seconds,
        "max_tokens": config.llm.max_tokens,
        "daily_token_budget": config.llm.daily_token_budget,
        "min_reply_interval": config.llm.min_reply_interval,
        "max_input_chars": config.llm.max_input_chars,
        "max_concurrent_requests": config.llm.max_concurrent_requests,
    })
    for name, values in (
        ("admin_users", config.permissions.admin_users),
        ("private_whitelist", config.permissions.private_whitelist),
        ("enabled_groups", config.permissions.enabled_groups),
    ):
        _validate_ids(name, values)

    quote = lambda value: json.dumps(value, ensure_ascii=False)
    ids = lambda values: "[" + ", ".join(str(value) for value in values) + "]"
    boolean = lambda value: "true" if value else "false"
    text = (
        "[connection]\n"
        f"url = {quote(config.connection.url)}\n"
        f"access_token = {quote(config.connection.access_token)}\n"
        f"reconnect_delay = {config.connection.reconnect_delay:g}\n\n"
        "[bot]\n"
        f"name = {quote(config.bot.name)}\n"
        f"echo = {boolean(config.bot.echo)}\n\n"
        "[features]\n"
        f"ping = {boolean(config.features.ping)}\n\n"
        "[permissions]\n"
        f"admin_users = {ids(config.permissions.admin_users)}\n"
        f"private_whitelist = {ids(config.permissions.private_whitelist)}\n"
        f"enabled_groups = {ids(config.permissions.enabled_groups)}\n\n"
        "[llm]\n"
        f"enabled = {boolean(config.llm.enabled)}\n"
        f"model = {quote(config.llm.model)}\n"
        f"timeout_seconds = {config.llm.timeout_seconds:g}\n"
        f"max_tokens = {config.llm.max_tokens}\n"
        f"daily_token_budget = {config.llm.daily_token_budget}\n"
        f"min_reply_interval = {config.llm.min_reply_interval:g}\n"
        f"max_input_chars = {config.llm.max_input_chars}\n"
        f"max_concurrent_requests = {config.llm.max_concurrent_requests}\n"
        "\n"
        "[notifications]\n"
        f"enabled = {boolean(config.notifications.enabled)}\n"
        f"night_sleep_enabled = {boolean(config.notifications.night_sleep_enabled)}\n"
        f"night_start = {quote(config.notifications.night_start)}\n"
        f"night_end = {quote(config.notifications.night_end)}\n"
        "\n"
        "[notifications.events]\n"
        f"translation = {boolean(config.notifications.events.translation)}\n"
        f"chat_reply = {boolean(config.notifications.events.chat_reply)}\n"
        f"login_failure = {boolean(config.notifications.events.login_failure)}\n"
        "\n"
        "[commands]\n"
        "\n"
        "[commands.aliases]\n"
        + "".join(
            f"{quote(key)} = {quote(value)}\n" for key, value in config.commands.aliases.items()
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + ".pending")
    try:
        pending.write_text(text, encoding="utf-8", newline="\n")
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    config.path = target
    return target


def _table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a TOML table")
    return value


def _string(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def _non_empty_string(section: dict[str, Any], key: str, default: str) -> str:
    value = _string(section, key, default).strip()
    if not value:
        raise ConfigError(f"{key} must not be empty")
    return value


def _boolean(section: dict[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    return value


def _number(section: dict[str, Any], key: str, default: float) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number")
    return float(value)



def _id_list(section: dict[str, Any], key: str) -> list[int]:
    values = section.get(key, [])
    if not isinstance(values, list):
        raise ConfigError(f"{key} must be an array of positive integers")
    result: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"{key} must contain only positive integers")
        result.append(value)
    return result


def _validate_ids(key: str, values: list[int]) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
        raise ConfigError(f"{key} must contain only positive integers")


def _validate_websocket_url(url: str) -> None:
    error = "connection.url must be a ws:// or wss:// address without embedded credentials, query, or fragment"
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ConfigError(error) from exc
    if (
        parsed.scheme not in {"ws", "wss"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(error)
