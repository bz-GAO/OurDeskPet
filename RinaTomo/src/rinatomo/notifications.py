"""Proactive push of '错过的事项' to admin users.

Template text only — never LLM-generated (铁律：不让桌宠即兴说话).
Receivers: exactly the admin_users whitelist, default-deny everything else.
"""

from __future__ import annotations

from .config import AppConfig

EVENT_KEYS = ("translation", "chat_reply", "login_failure")


def evaluate_gate(config: AppConfig, event: str) -> str | None:
    """Return a rejection reason, or None when the push may proceed."""
    if event not in EVENT_KEYS:
        return "未知通知事件"
    if not config.notifications.enabled:
        return "通知已关闭"
    if not getattr(config.notifications.events, event, False):
        return "该事件类型未开启推送"
    admins = config.permissions.admin_users
    if not admins:
        return "未配置 admin_users，无法推送"
    return None


def format_notification(title: str, lines: list[str]) -> str:
    header = f"【{title.strip()[:80]}】" if title.strip() else "[RinaTomo]"
    body = [line.strip()[:200] for line in lines if line.strip()]
    return "\n".join([header, *body])[:1500]
