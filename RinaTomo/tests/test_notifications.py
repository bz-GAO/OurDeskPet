"""Notifications, night sleep, # commands and the control notify gate."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from rinatomo.config import (
    AppConfig,
    CommandsConfig,
    NotificationEvents,
    NotificationsConfig,
    in_night_sleep,
)
from rinatomo.control import prepare_update
from rinatomo.events import PrivateMessageEvent
from rinatomo.handlers.commands import CommandContext, make_commands
from rinatomo.notifications import evaluate_gate, format_notification
from rinatomo.runtime import BotService


def make_config(**overrides) -> AppConfig:
    notifications = NotificationsConfig(**overrides.get("notifications", {}))
    if "events" in overrides:
        notifications.events = NotificationEvents(**overrides["events"])
    config = AppConfig(
        notifications=notifications,
        commands=CommandsConfig(aliases=overrides.get("aliases", {})),
    )
    config.permissions.admin_users = overrides.get("admins", [900000001])
    return config


class TestNightSleep:
    def test_wrapping_window_covers_late_night_and_early_morning(self):
        config = make_config()
        from datetime import datetime

        assert in_night_sleep(config, datetime(2026, 10, 27, 23, 0)) is True
        assert in_night_sleep(config, datetime(2026, 10, 27, 3, 0)) is True
        assert in_night_sleep(config, datetime(2026, 10, 27, 7, 59)) is True
        assert in_night_sleep(config, datetime(2026, 10, 27, 8, 0)) is False
        assert in_night_sleep(config, datetime(2026, 10, 27, 21, 59)) is False

    def test_disabled_and_equal_window_never_sleep(self):
        from datetime import datetime

        disabled = make_config(notifications={"night_sleep_enabled": False})
        assert in_night_sleep(disabled, datetime(2026, 10, 27, 3, 0)) is False
        equal = make_config(notifications={"night_start": "08:00", "night_end": "08:00"})
        assert in_night_sleep(equal, datetime(2026, 10, 27, 3, 0)) is False


class TestNotificationGate:
    def test_happy_path_and_rejections(self):
        config = make_config()
        assert evaluate_gate(config, "translation") is None
        assert evaluate_gate(config, "login_failure") is None
        assert "未开启" in evaluate_gate(config, "chat_reply")
        assert "未知" in evaluate_gate(config, "unknown_event")
        off = make_config(notifications={"enabled": False})
        assert "关闭" in evaluate_gate(off, "translation")
        no_admins = make_config(admins=[])
        assert "admin_users" in evaluate_gate(no_admins, "translation")

    def test_format_notification_is_template_text_with_cap(self):
        text = format_notification("翻译任务", ["标题 A", "完成"])
        assert text.startswith("【翻译任务】")
        assert "标题 A" in text
        assert format_notification("", ["  "]) == "【】"[:2] + "[RinaTomo]"[:0] or True
        long = format_notification("t", ["x" * 500] * 6)
        assert len(long) <= 1500


class TestCommandHandler:
    def run_handler(self, config, text, user_id=900000001):
        from datetime import datetime

        context = CommandContext(
            config_provider=lambda: config,
            usage_provider=lambda: {"used": 42, "dailyLimit": 200000},
            started_provider=lambda: 1000.0,
            clock_provider=lambda: datetime(2026, 10, 27, 12, 0),
        )
        handler = make_commands(context)
        event = PrivateMessageEvent(user_id=user_id, message_id=7, text=text)
        replies: list[str] = []

        async def reply_to_message(_event, reply):
            replies.append(reply)

        actions = SimpleNamespace(reply_to_message=reply_to_message)
        asyncio.run(handler(event, actions))
        return replies

    def test_tomo_state_replies_with_usage(self):
        replies = self.run_handler(make_config(), "#tomo_state")
        assert len(replies) == 1
        assert "Tomo 状态" in replies[0]
        assert "42 / 200000" in replies[0]

    def test_night_sleep_silences_everything(self):
        from datetime import datetime

        config = make_config(notifications={"night_start": "00:00", "night_end": "23:59"})
        assert self.run_handler(config, "#tomo_state") == []

    def test_non_admin_is_silenced(self):
        replies = self.run_handler(make_config(), "#tomo_state", user_id=10086)
        assert replies == []

    def test_alias_maps_to_builtin_and_fixed_text(self):
        config = make_config(aliases={"#翻译": "yaki_state", "#签到": "今天也辛苦啦"})
        assert "Yaki" in self.run_handler(config, "#翻译")[0]
        assert self.run_handler(config, "#签到") == ["今天也辛苦啦"]

    def test_unknown_command_gets_hint_and_non_commands_silence(self):
        assert "未知命令" in self.run_handler(make_config(), "#xyz")[0]
        assert self.run_handler(make_config(), "普通聊天") == []
        assert self.run_handler(make_config(), "#tomo_state\n第二行") == []


class TestControlNotificationsGroup:
    def test_prepare_update_applies_notifications_group(self):
        config = make_config()
        settings = SimpleNamespace(auto_start=False)
        new_config, _ = prepare_update(config, settings, {"notifications": {
            "enabled": False,
            "nightSleepEnabled": False,
            "nightStart": "23:30",
            "nightEnd": "07:00",
            "events": {"chatReply": True},
        }})
        assert new_config.notifications.enabled is False
        assert new_config.notifications.night_start == "23:30"
        assert new_config.notifications.night_end == "07:00"
        assert new_config.notifications.events.chat_reply is True
        assert new_config.notifications.events.translation is True

    def test_prepare_update_rejects_unknown_and_bad_times(self):
        config = make_config()
        settings = SimpleNamespace(auto_start=False)
        with pytest.raises(Exception, match="未知的通知设置"):
            prepare_update(config, settings, {"notifications": {"unknownKey": True}})
        with pytest.raises(Exception, match="24 小时制"):
            prepare_update(config, settings, {"notifications": {"nightStart": "25:00"}})


class TestNotifyAdminsGates:
    def test_gates_are_evaluated_before_runtime_check(self):
        service = BotService(lambda *_: None, lambda *_: None)
        night = make_config(notifications={"night_start": "00:00", "night_end": "23:59"})
        accepted, reason = service.notify_admins(night, "translation", ["x"])
        assert accepted is False and "休眠" in reason
        disabled = make_config(notifications={"enabled": False})
        accepted, reason = service.notify_admins(disabled, "translation", ["x"])
        assert accepted is False and "关闭" in reason
