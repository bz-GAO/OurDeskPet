"""Canonical subtitle documents and deterministic text subtitle exporters."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from PIL import ImageFont

from .workspace import safe_project_name
from .styling import DEFAULT_FONT, GENSEN_FONT, validate_styles, ass_color


SubtitleMode = Literal["source", "translated", "bilingual"]
SUPPORTED_FORMATS = ("json", "srt", "vtt", "ass")


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    cue_id: str
    start_ms: int
    end_ms: int
    source_text: str
    translation: str | None = None
    speaker_id: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.cue_id:
            raise ValueError("cue_id must not be empty")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError(f"invalid time range for {self.cue_id}")
        if not self.source_text.strip():
            raise ValueError(f"source_text must not be empty for {self.cue_id}")


@dataclass(frozen=True, slots=True)
class SubtitleDocument:
    source_language: str
    target_language: str
    cues: tuple[SubtitleCue, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        previous_start = -1
        seen: set[str] = set()
        for cue in self.cues:
            if cue.cue_id in seen:
                raise ValueError(f"duplicate cue id: {cue.cue_id}")
            if cue.start_ms < previous_start:
                raise ValueError(f"unordered cue: {cue.cue_id}")
            seen.add(cue.cue_id)
            previous_start = cue.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "metadata": dict(self.metadata),
            "cues": [
                {
                    "id": cue.cue_id,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms,
                    "source_text": cue.source_text,
                    "translation": cue.translation,
                    "speaker_id": cue.speaker_id,
                    "confidence": cue.confidence,
                }
                for cue in self.cues
            ],
        }


def load_subtitle_document(path: Path, *, target_language: str = "zh-Hans") -> SubtitleDocument:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if "cues" in payload:
        return _from_canonical_payload(payload)
    if "segments" in payload:
        return _from_asr_payload(payload, target_language=target_language)
    raise ValueError("input JSON must contain either 'cues' or 'segments'")


def _from_canonical_payload(payload: Mapping[str, Any]) -> SubtitleDocument:
    cues = tuple(
        SubtitleCue(
            cue_id=str(item["id"]),
            start_ms=int(item["start_ms"]),
            end_ms=int(item["end_ms"]),
            source_text=str(item["source_text"]),
            translation=item.get("translation"),
            speaker_id=item.get("speaker_id"),
            confidence=item.get("confidence"),
        )
        for item in payload["cues"]
    )
    return SubtitleDocument(
        schema_version=int(payload.get("schema_version", 1)),
        source_language=str(payload.get("source_language", "ja")),
        target_language=str(payload.get("target_language", "zh-Hans")),
        metadata=payload.get("metadata") or {},
        cues=cues,
    )


def _from_asr_payload(
    payload: Mapping[str, Any], *, target_language: str
) -> SubtitleDocument:
    cues = tuple(
        SubtitleCue(
            cue_id=str(item["id"]),
            start_ms=int(item["start_ms"]),
            end_ms=int(item["end_ms"]),
            source_text=str(item["text"]),
            speaker_id=item.get("speaker_id"),
            confidence=item.get("confidence"),
        )
        for item in payload["segments"]
    )
    return SubtitleDocument(
        source_language=str(payload.get("language", "ja")),
        target_language=target_language,
        metadata={"asr_model": payload.get("model"), "imported_from": "asr_segments"},
        cues=cues,
    )


def _cue_text(cue: SubtitleCue, mode: SubtitleMode) -> str:
    if mode == "source":
        return cue.source_text.strip()
    if not cue.translation or not cue.translation.strip():
        raise ValueError(f"cue {cue.cue_id} has no translation for mode '{mode}'")
    if mode == "translated":
        return cue.translation.strip()
    return f"{cue.source_text.strip()}\n{cue.translation.strip()}"


def _clock(milliseconds: int, decimal: str, *, ass: bool = False) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    if ass:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{millis // 10:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{decimal}{millis:03d}"


def render_srt(document: SubtitleDocument, *, mode: SubtitleMode) -> str:
    blocks = []
    for index, cue in enumerate(document.cues, start=1):
        blocks.append(
            f"{index}\n"
            f"{_clock(cue.start_ms, ',')} --> {_clock(cue.end_ms, ',')}\n"
            f"{_cue_text(cue, mode)}"
        )
    return "\n\n".join(blocks) + "\n"


def render_vtt(document: SubtitleDocument, *, mode: SubtitleMode) -> str:
    blocks = ["WEBVTT"]
    for cue in document.cues:
        blocks.append(
            f"{cue.cue_id}\n"
            f"{_clock(cue.start_ms, '.')} --> {_clock(cue.end_ms, '.')}\n"
            f"{_cue_text(cue, mode)}"
        )
    return "\n\n".join(blocks) + "\n"


def _ass_escape(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = normalized.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    return escaped.replace("\n", r"\N")


@lru_cache(maxsize=8)
def _subtitle_font(region: str, size: int, font_name: str | None = None):
    filename = ('GenSenRounded2JP-M.otf' if font_name == GENSEN_FONT
                else f'NotoSansCJK{region}-Medium.otf')
    path = Path(__file__).resolve().parents[2] / 'assets' / 'fonts' / filename
    return ImageFont.truetype(str(path), size)


def _wrap_screen_text(text: str, *, region: str, size: int,
                      font_name: str | None = None, max_width: int = 1280) -> str:
    """Wrap display text near two thirds of the 1920px ASS canvas, preserving cue timing."""
    font = _subtitle_font(region, size, font_name)
    lines = []
    for original in text.splitlines():
        remaining = original.strip()
        while remaining and font.getlength(remaining) > max_width:
            end = 1
            while end < len(remaining) and font.getlength(remaining[:end + 1]) <= max_width:
                end += 1
            # Prefer a natural pause near the right edge; never split the timed cue.
            choices = [index + 1 for index, char in enumerate(remaining[:end])
                       if char in ' 、。，。！？；：,.!?;:' or char.isspace()]
            near = [index for index in choices if index >= end * .55]
            cut = near[-1] if near else end
            lines.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            lines.append(remaining)
    return '\n'.join(lines)


def render_ass(
    document: SubtitleDocument,
    *,
    mode: SubtitleMode,
    font_name: str = "Noto Sans CJK SC Medium",
    source_font_name: str = "Noto Sans CJK JP Medium",
) -> str:
    if document.target_language == 'ja' and font_name == 'Noto Sans CJK SC Medium':
        font_name = 'Noto Sans CJK JP Medium'
    if document.source_language in {'zh', 'zh-Hans', 'en'} and source_font_name == 'Noto Sans CJK JP Medium':
        source_font_name = 'Noto Sans CJK SC Medium'
    source_region = 'sc' if source_font_name == 'Noto Sans CJK SC Medium' else 'jp'
    target_region = 'jp' if font_name == 'Noto Sans CJK JP Medium' else 'sc'
    header = f"""[Script Info]
; Generated by RinaYaki. Edit the canonical JSON instead of this generated view.
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Translation,{font_name},68,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2.5,1.5,2,100,100,55,1
Style: Source,{source_font_name},48,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,1.6,0.5,2,100,100,55,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    styles = validate_styles(document.metadata.get('speaker_styles',{}))
    for cue in document.cues:
        speaker = (cue.speaker_id or "").replace(",", "，")
        selected = styles.get(cue.speaker_id if cue.speaker_id is not None else 'unknown',{})
        outline = selected.get('color')
        selected_font = selected.get('font', font_name)
        if selected_font == DEFAULT_FONT and font_name == 'Noto Sans CJK JP Medium':
            selected_font = font_name
        outline_override = (r'\3c' + ass_color(outline)) if outline else ''
        font_override = (r'\fn' + selected_font) if selected_font != font_name else ''
        target_override = ('{' + outline_override + font_override + '}') if outline_override or font_override else ''
        source_override = ('{' + outline_override + '}') if outline_override else ''
        if mode == "bilingual":
            _cue_text(cue, mode)
            text = (
                r"{\rSource}"
                + source_override
                + _ass_escape(_wrap_screen_text(cue.source_text, region=source_region, size=48))
                + r"\N{\rTranslation}"
                + target_override
                + _ass_escape(_wrap_screen_text(cue.translation or "", region=target_region, size=68,
                                                font_name=selected_font))
            )
        else:
            region, size = (source_region, 48) if mode == 'source' else (target_region, 68)
            override = source_override if mode == 'source' else target_override
            wrap_font = None if mode == 'source' else selected_font
            text = override + _ass_escape(_wrap_screen_text(_cue_text(cue, mode), region=region,
                                                             size=size, font_name=wrap_font))
        style = "Source" if mode == "source" else "Translation"
        events.append(
            "Dialogue: 0,"
            f"{_clock(cue.start_ms, '.', ass=True)},"
            f"{_clock(cue.end_ms, '.', ass=True)},"
            f"{style},{speaker},0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def export_subtitles(
    document: SubtitleDocument,
    output_dir: Path,
    *,
    stem: str,
    formats: Iterable[str] = SUPPORTED_FORMATS,
    mode: SubtitleMode = "source",
    font_name: str = "Noto Sans CJK SC Medium",
) -> tuple[Path, ...]:
    safe_stem = safe_project_name(stem)
    requested = tuple(dict.fromkeys(formats))
    unknown = set(requested) - set(SUPPORTED_FORMATS)
    if unknown:
        raise ValueError(f"unsupported subtitle formats: {', '.join(sorted(unknown))}")
    output_dir.mkdir(parents=True, exist_ok=True)
    language_tag = {
        "source": document.source_language,
        "translated": document.target_language,
        "bilingual": f"{document.source_language}-{document.target_language}",
    }[mode]
    if document.source_language == document.target_language and mode in {'source', 'translated'}:
        language_tag += '.' + mode
    written: list[Path] = []
    for format_name in requested:
        if format_name == "json":
            path = output_dir / f"{safe_stem}.subtitles.json"
            content = json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n"
        else:
            path = output_dir / f"{safe_stem}.{language_tag}.{format_name}"
            if format_name == "srt":
                content = render_srt(document, mode=mode)
            elif format_name == "vtt":
                content = render_vtt(document, mode=mode)
            else:
                content = render_ass(document, mode=mode, font_name=font_name)
        temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        written.append(path)
    return tuple(written)
