"""Standalone entry point: ``python -m rinayaki.live``.

Runs the realtime chain in its own process, separate from the offline
launcher. Shared API/model/interval settings come from ``rinayaki.settings``
(the same store the offline UI writes); the native UI launches this entry
point with live-only settings as explicit command line flags.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import time

from ..cloud_asr import STREAMING_MODEL
from ..languages import SOURCE_LABELS, TARGET_LABELS
from ..settings import load_settings
from ..settings import LIVE_ENGINES
from ..styling import DEFAULT_FONT, PRESETS, register_private_fonts
from ..guidance import Guidance, load_guidance
from . import events as ev
from .capture import list_loopback_devices
from .coordinator import RealtimeCoordinator
from .session import DISPLAY_MODES, LiveSettings, open_live_session


def _parse_language(value: str, table: dict[str, str], label: str) -> str:
    value = value.strip()
    if value in table.values():
        return value
    if value in table:
        return table[value]
    raise SystemExit(f"{label}不支持：{value}（可用：{', '.join(table)}）")


def _positive_duration(value: str) -> float:
    duration = float(value)
    if duration <= 0:
        raise argparse.ArgumentTypeError("运行时长必须大于 0 秒")
    return duration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rinayaki.live",
        description="RinaYaki 实时翻译（系统声音 loopback 采集，独立于离线流水线）",
    )
    parser.add_argument("--list-devices", action="store_true", help="列出可用的系统声音采集设备后退出")
    parser.add_argument("--device", default=None, help="输出设备 ID 或名称片段（默认跟随系统默认输出设备）")
    parser.add_argument("--latency", choices=("low", "balanced", "quality"), default="balanced", help="延迟偏好")
    parser.add_argument("--source", default="ja", help="输入语言（ja/zh/en 或 中文/日本語/English）")
    parser.add_argument("--target", default="zh-Hans", help="输出语言（zh-Hans/en/ja 或 简体中文/English/日本語）")
    parser.add_argument("--no-record", action="store_true", help="不保存会话录音")
    parser.add_argument("--translation-engine", choices=sorted(LIVE_ENGINES), default=None,
                        help="实时翻译方式（默认使用设置页的选择）")
    parser.add_argument("--display-mode", choices=sorted(DISPLAY_MODES), default="bilingual", help="显示原文、译文或双语；source 模式不会调用翻译 API")
    parser.add_argument("--font-family", default=DEFAULT_FONT, help="结果窗口字幕字体")
    parser.add_argument("--guidance-pack", action="append", default=[], help="本会话启用的术语包 ID，可重复")
    parser.add_argument("--allow-draft-guidance", action="store_true", help="明确允许本会话试用选中的草案术语包")
    parser.add_argument("--font-size", type=int, default=14, help="字幕字号（pt，10–96）；双语原文使用较小字号")
    parser.add_argument("--subtitle-color", default=PRESETS['默认'], help="原文和译文共用的六位描边颜色")
    parser.add_argument("--subtitle-lines", type=int, default=8, help="结果窗口保留的条数")
    parser.add_argument("--no-window", action="store_true", help="无窗口模式，翻译输出到控制台")
    parser.add_argument("--dry-run", action="store_true", help="链路自检：采集与落盘照常，识别用空实现，不调用付费 API")
    parser.add_argument("--session-name", default=None, help="会话目录后缀名")
    parser.add_argument("--duration", type=_positive_duration, default=None, help="最长运行秒数（到时自动停止，便于试跑）")
    parser.add_argument("--project-root", type=Path, default=None, help="RinaYaki 项目根目录（默认自动推断）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.list_devices:
        for device in list_loopback_devices():
            flag = "loopback" if device["is_loopback"] else "input"
            print(f"{device['id']}\n    {device['name']} ({flag})")
        return 0

    project_root = (args.project_root or Path(__file__).resolve().parents[3]).resolve()
    shared = load_settings(project_root)
    live = LiveSettings(
        translation_engine=args.translation_engine or shared.live_engine,
        audio_device=args.device,
        latency=args.latency,
        source_language=_parse_language(args.source, SOURCE_LABELS, "输入语言"),
        target_language=_parse_language(args.target, TARGET_LABELS, "输出语言"),
        record_session=not args.no_record,
        display_mode=args.display_mode,
        subtitle_lines=args.subtitle_lines,
        subtitle_font_family=args.font_family,
        subtitle_font_size=args.font_size,
        subtitle_color=args.subtitle_color,
        guidance_packs=tuple(args.guidance_pack),
        allow_draft_guidance=args.allow_draft_guidance,
    )
    if not args.dry_run and not shared.api_key:
        print("未配置 DASHSCOPE_API_KEY：请先运行 RinaYaki 的设置流程。", file=sys.stderr)
        return 2

    guidance = Guidance()
    if live.translation_enabled and live.guidance_packs:
        if not live.uses_livetranslate and not shared.translation_model.startswith('qwen-mt-'):
            raise ValueError('术语指导目前仅支持 Qwen-MT 翻译模型。')
        guidance = load_guidance(project_root,live.guidance_packs,live.source_language,
                                 live.target_language,allow_draft=live.allow_draft_guidance)
    paths = open_live_session(project_root, live, args.session_name)
    bus = ev.EventBus()
    coordinator = RealtimeCoordinator(live, shared, paths, bus=bus, dry_run=args.dry_run,guidance=guidance)
    asr_label = "dry-run（不调用 API）" if args.dry_run else coordinator.model
    print(f"会话目录：{paths.summary()}")
    translation_label = (coordinator.model if live.uses_livetranslate else shared.translation_model) if live.translation_enabled else "关闭（仅识别原文）"
    print(f"实时识别：{asr_label} · 翻译：{translation_label}"
          f" · 间隔 {shared.minimum_interval_seconds}s · 延迟偏好 {live.latency}")
    print("关闭窗口或按 Ctrl+C 结束会话。")

    event_log = ev.EventLog(paths.events_jsonl)
    bus.subscribe(event_log.handle)

    if args.no_window:
        from .sinks.console import ConsoleSink

        bus.subscribe(ConsoleSink(display_mode=live.display_mode).handle)
        threading.Thread(target=_start_quietly, args=(coordinator,), daemon=True).start()
        stop_reason = "console-stop"
        try:
            deadline = time.monotonic() + args.duration if args.duration else None
            while not coordinator.wait_until_stopped(0.2):
                if deadline is not None and time.monotonic() >= deadline:
                    stop_reason = f"到达 --duration {args.duration}s"
                    break
        except KeyboardInterrupt:
            print("\n正在结束会话…")
            stop_reason = "keyboard-interrupt"
        stats = coordinator.stop(stop_reason)
        event_log.close()
        print(f"已保存：{paths.summary()}\n统计：{stats}")
        return 0

    from .sinks.subtitle_window import SubtitleWindow

    register_private_fonts(project_root / 'assets/fonts')

    window = SubtitleWindow(
        lines=live.subtitle_lines,
        font_size=live.subtitle_font_size,
        font_family=live.subtitle_font_family,
        subtitle_color=live.normalized_subtitle_color,
        display_mode=live.display_mode,
        session_name=args.session_name,
        record_session=live.record_session,
        on_close=coordinator.request_stop,
        on_pause=coordinator.request_pause,
    )
    bus.subscribe(window.handle)
    threading.Thread(target=_start_quietly, args=(coordinator,), daemon=True).start()
    if args.duration:
        threading.Thread(target=_timed_stop, args=(coordinator, args.duration), daemon=True).start()
    window.run()
    event_log.close()
    print(f"已保存：{paths.summary()}\n统计：{coordinator.stats}")
    return 0


def _start_quietly(coordinator: RealtimeCoordinator) -> None:
    try:
        coordinator.start()
    except Exception:
        # RealtimeCoordinator already emitted a sanitized runtime error and
        # completed best-effort cleanup before propagating the exception.
        return


def _timed_stop(coordinator: RealtimeCoordinator, seconds: float) -> None:
    if not coordinator.wait_until_stopped(seconds):
        coordinator.request_stop(f"到达 --duration {seconds}s")


if __name__ == "__main__":
    raise SystemExit(main())
