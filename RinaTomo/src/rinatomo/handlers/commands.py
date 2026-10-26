"""# 状态查询命令：默认拒绝、仅 admin、深夜休眠期间完全静默。

行为逻辑住在独立 handler 模块（见 handlers/debug.py 的注释约定）。
别名支持：config.commands.aliases 把 #别名 映射到内置命令名或固定回复文本。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import subprocess
import time as time_module
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..actions import Actions
from ..config import AppConfig, in_night_sleep
from ..events import Event, GroupMessageEvent, MessageEvent, PrivateMessageEvent

log = logging.getLogger(__name__)

BUILTIN = ("yaki_state", "tomo_state", "help")
STATUS_LABEL = {
    "running": "进行中",
    "new": "排队中",
    "awaiting_style": "翻译完成待导出",
    "failed": "失败",
    "complete": "已完成",
}


@dataclass
class CommandContext:
    """Providers injected by the runtime so handlers always see live state."""

    config_provider: Callable[[], AppConfig]
    usage_provider: Callable[[], dict[str, int] | None]
    started_provider: Callable[[], float | None]
    clock_provider: Callable[[], dt.datetime] = lambda: dt.datetime.now()


def _is_admin(event: Event, config: AppConfig) -> bool:
    if isinstance(event, (PrivateMessageEvent, GroupMessageEvent)):
        return event.user_id in config.permissions.admin_users
    return False


def _yaki_root() -> Path | None:
    override = os.environ.get("RINAYAKI_ROOT", "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    else:
        root = Path(__file__).resolve().parents[2]
        candidates.append(root.parent / "RinaYaki")
    for candidate in candidates:
        if (candidate / "scripts" / "desk_bridge.py").is_file():
            return candidate
    return None


def _yaki_jobs() -> str:
    """Read-only bridge call; runs in a worker thread via asyncio.to_thread."""
    root = _yaki_root()
    if root is None:
        return "Yaki 未接入（未找到 RinaYaki 目录，可用 RINAYAKI_ROOT 指定）"
    python = root / ".venv" / "Scripts" / "python.exe"
    bridge = root / "scripts" / "desk_bridge.py"
    if not python.is_file() or not bridge.is_file():
        return "Yaki 桥接口不可用，请检查 RinaYaki 安装"
    payload = json.dumps({"action": "jobs", "request": {}})
    try:
        result = subprocess.run(
            [str(python), "-X", "utf8", str(bridge), "action", payload],
            capture_output=True,
            timeout=25,
            cwd=root,
        )
    except subprocess.TimeoutExpired:
        return "Yaki 查询超时"
    try:
        value = json.loads(result.stdout.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return "Yaki 返回内容无法解析"
    jobs = value.get("jobs")
    if not isinstance(jobs, list):
        return "Yaki 暂无任务记录"
    if not jobs:
        return "当前没有 Yaki 翻译任务"
    lines = ["Yaki 任务："]
    for job in jobs[-5:]:
        state = job.get("state", {})
        status = STATUS_LABEL.get(str(state.get("status", "")), str(state.get("status", "未知")))
        detail = str(state.get("stage", "") or "")
        percent = ""
        total = state.get("total")
        if isinstance(total, (int, float)) and total > 0 and isinstance(state.get("completed"), (int, float)):
            percent = f" {round(100 * state['completed'] / total)}%"
        lines.append(f"▸ {job.get('projectName', '?')} — {status}{(' · ' + detail) if detail else ''}{percent}")
    return "\n".join(lines)


def _tomo_state(context: CommandContext) -> str:
    lines = ["Tomo 状态："]
    started = context.started_provider()
    if started:
        seconds = max(0, int(time_module.time() - started))
        hours, rest = divmod(seconds, 3600)
        lines.append(f"已运行 {hours} 小时 {rest // 60} 分")
    usage = context.usage_provider()
    if usage:
        lines.append(f"今日 token {usage.get('used', 0)} / {usage.get('dailyLimit', 0)}")
    else:
        lines.append("服务未运行，无用量数据")
    return "\n".join(lines)


def make_commands(context: CommandContext):
    """Build the # command handler bound to a live context."""

    async def commands_handler(event: Event, actions: Actions) -> None:
        config = context.config_provider()
        # 深夜休眠：即使开着也不服务——静默忽略，不回复不处理。
        if in_night_sleep(config, context.clock_provider()):
            return
        if not isinstance(event, (PrivateMessageEvent, GroupMessageEvent)):
            return
        text = event.text.strip()
        if not text.startswith("#") or len(text) > 64 or "\n" in text:
            return
        if not _is_admin(event, config):
            return
        key = "#" + text[1:].strip().lower()
        aliased = key in config.commands.aliases
        builtin = key[1:]
        target = config.commands.aliases.get(key, builtin if builtin in BUILTIN else None)
        if aliased and target not in BUILTIN:
            await actions.reply_to_message(event, target or "")
            return
        if target == "help":
            builtin = "、".join(f"#{name}" for name in BUILTIN)
            await actions.reply_to_message(event, f"可用命令：{builtin}")
            return
        if target == "tomo_state":
            await actions.reply_to_message(event, _tomo_state(context))
            return
        if target == "yaki_state":
            reply = await asyncio.to_thread(_yaki_jobs)
            await actions.reply_to_message(event, reply)
            return
        if target:
            await actions.reply_to_message(event, target)
            return
        await actions.reply_to_message(event, "未知命令。#help 查看可用命令")

    return commands_handler
