"""Live session configuration and on-disk session store.

Live sessions live under ``workspaces/live/<timestamp>-<name>/`` and are
fully independent from offline ``project.json`` jobs. A session directory
contains the recorded 16 kHz mono PCM WAV (the exact stream the realtime
ASR consumed, ready for later offline re-transcription), an ``events.jsonl``
timeline, ``session.json`` provenance and a human-readable transcript.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re

from ..languages import validate_languages
from ..styling import DEFAULT_FONT, PRESETS, normalize_color
from ..settings import DEFAULT_LIVE_ENGINE, LIVE_ENGINES


LATENCY_PRESETS_MS = {"low": 100, "balanced": 200, "quality": 320}
DISPLAY_MODES = {"source", "translation", "bilingual"}


@dataclass(frozen=True, slots=True)
class LiveSettings:
    """Live-only configuration. Shared API/model settings stay in UserSettings."""

    audio_device: str | None = None
    latency: str = "balanced"
    source_language: str = "ja"
    target_language: str = "zh-Hans"
    record_session: bool = True
    display_mode: str = "bilingual"
    subtitle_lines: int = 4
    subtitle_font_size: int = 14
    subtitle_font_family: str = DEFAULT_FONT
    subtitle_color: str = PRESETS['默认']
    translation_queue_capacity: int = 6
    guidance_packs: tuple[str, ...] = ()
    allow_draft_guidance: bool = False
    translation_engine: str = DEFAULT_LIVE_ENGINE

    def __post_init__(self) -> None:
        if self.translation_engine not in LIVE_ENGINES:
            raise ValueError("实时翻译方式无效。")
        if len(self.guidance_packs)>16 or any(not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',value) for value in self.guidance_packs):
            raise ValueError('术语包 ID 或数量无效。')
        if self.latency not in LATENCY_PRESETS_MS:
            raise ValueError("延迟偏好仅支持 low、balanced、quality。")
        validate_languages(self.source_language, self.target_language)
        if self.display_mode not in DISPLAY_MODES:
            raise ValueError("显示模式仅支持 source、translation、bilingual。")
        if self.subtitle_lines < 1 or self.subtitle_lines > 20:
            raise ValueError("字幕窗口保留行数须在 1 到 20 之间。")
        if self.subtitle_font_size < 10 or self.subtitle_font_size > 96:
            raise ValueError("字幕字号须在 10 到 96 之间。")
        font = self.subtitle_font_family.strip()
        if not font or len(font) > 120 or any(ord(character) < 32 for character in font):
            raise ValueError("字幕字体名称无效。")
        normalize_color(self.subtitle_color)
        if self.translation_queue_capacity < 1 or self.translation_queue_capacity > 64:
            raise ValueError("实时翻译队列容量须在 1 到 64 之间。")

    @property
    def frame_ms(self) -> int:
        return LATENCY_PRESETS_MS[self.latency]

    @property
    def translation_enabled(self) -> bool:
        return self.display_mode != "source"

    @property
    def normalized_subtitle_color(self) -> str:
        return normalize_color(self.subtitle_color)

    @property
    def uses_livetranslate(self) -> bool:
        # Source-only sessions must not accidentally pay for translation.
        return self.translation_enabled and self.translation_engine == "livetranslate"

    def public(self) -> dict:
        return {
            "audio_device": self.audio_device or "default-loopback",
            "latency": self.latency,
            "frame_ms": self.frame_ms,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "record_session": self.record_session,
            "display_mode": self.display_mode,
            "subtitle_lines": self.subtitle_lines,
            "subtitle_font_size": self.subtitle_font_size,
            "subtitle_font_family": self.subtitle_font_family.strip(),
            "subtitle_color": self.normalized_subtitle_color,
            "translation_enabled": self.translation_enabled,
            "translation_engine": self.translation_engine if self.translation_enabled else "asr-only",
            "translation_queue_capacity": self.translation_queue_capacity,
            "guidance_packs": list(self.guidance_packs) if self.translation_enabled else [],
            "allow_draft_guidance": self.allow_draft_guidance if self.translation_enabled else False,
        }


def _slugify(name: str | None) -> str:
    if not name:
        return ""
    slug = re.sub(r'[\\/:*?"<>|\s]+', "-", name.strip())
    return slug[:60].strip("-")


@dataclass(frozen=True, slots=True)
class SessionPaths:
    root: Path
    audio_wav: Path
    events_jsonl: Path
    transcript_txt: Path
    session_json: Path

    def summary(self) -> str:
        return str(self.root)


def open_live_session(project_root: Path, settings: LiveSettings, name: str | None = None) -> SessionPaths:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(name)
    parent = project_root / "workspaces" / "live"
    base_name = f"{stamp}-{slug}" if slug else stamp
    parent.mkdir(parents=True, exist_ok=True)
    for suffix in range(1000):
        candidate = base_name if suffix == 0 else f"{base_name}-{suffix:02d}"
        root = parent / candidate
        try:
            root.mkdir(exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("同一秒内创建的直播会话过多。")
    paths = SessionPaths(
        root=root,
        audio_wav=root / "audio" / "raw-16k-mono.wav",
        events_jsonl=root / "events.jsonl",
        transcript_txt=root / "transcript.txt",
        session_json=root / "session.json",
    )
    write_session_record(paths, settings, {}, {}, status="created")
    return paths


def write_session_record(
    paths: SessionPaths,
    settings: LiveSettings,
    provenance: dict,
    stats: dict,
    *,
    status: str = "ended",
    ended_reason: str | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    try:
        previous = json.loads(paths.session_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    record = {
        "schema_version": 1,
        "created": previous.get("created", now),
        "updated": now,
        "status": status,
        "ended_reason": ended_reason,
        "settings": settings.public(),
        "provenance": provenance,
        "stats": stats,
        "paths": {
            "audio": (
                str(paths.audio_wav.relative_to(paths.root)) if settings.record_session else None
            ),
            "events": str(paths.events_jsonl.relative_to(paths.root)),
            "transcript": str(paths.transcript_txt.relative_to(paths.root)),
        },
    }
    _atomic_write_text(paths.session_json, json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def write_transcript(paths: SessionPaths, entries: list[dict]) -> None:
    """entries: [{start_ms, end_ms, source, translation}] already ordered."""
    def clock(ms: int) -> str:
        seconds = max(0, int(ms)) // 1000
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

    lines = []
    for entry in entries:
        if entry.get("source"):
            lines.append(f"[{clock(entry['start_ms'])}] {entry['source']}".rstrip())
        if entry.get("translation"):
            prefix = "           " if entry.get("source") else f"[{clock(entry['start_ms'])}] "
            lines.append(prefix + entry['translation'])
    _atomic_write_text(paths.transcript_txt, "\n".join(lines) + ("\n" if lines else ""))


def _atomic_write_text(path: Path, text: str) -> None:
    pending = path.with_name(path.name + ".pending")
    try:
        pending.write_text(text, encoding="utf-8", newline="\n")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)
