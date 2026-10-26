"""Run one resumable YouTube -> ASR -> translation -> subtitles -> MKV pipeline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import hashlib
import os
import time
import uuid
from pathlib import Path
import re
import subprocess
import sys
import shutil
from contextlib import nullcontext
from typing import Any, Iterable

from rinayaki.languages import NAMES, asr_hints, validate_languages
from rinayaki.acquisition import acquire
from rinayaki.job import RUN_DIRECTORY, PROGRESS_FILE, report_progress, archive_attempt, file_digest, fingerprint, job_lock, read_cached
from rinayaki.styling import validate_styles, speaker_samples
from rinayaki.cue_segmentation import source_cues_from_asr
from rinayaki.project_storage import lifecycle_lock
from rinayaki.settings import DEFAULT_ASR_MODEL, UserSettings, apply_runtime_snapshot, load_settings, runtime_environment
from rinayaki.workspace import safe_project_name
from rinayaki.cloud_asr import QwenAudioAsrClient
from rinayaki.billing import reconcile_project as reconcile_project_billing
from rinayaki.subtitles import SubtitleCue, SubtitleDocument, export_subtitles, render_ass
from rinayaki.translation import (
    DashScopeApiError,
    DashScopeOpenAIClient,
    qwen_mt_payload,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ffmpeg_filter_path(path: Path) -> str:
    """Escape an unquoted path through the option and filtergraph parsers."""
    value = path.resolve().as_posix()
    # FFmpeg parses the graph first, then each filter's option values. A quoted
    # string alone does not preserve apostrophes through both parsing layers.
    for special in ("\\':", "\\'[],;"):
        value = "".join("\\" + character if character in special else character for character in value)
    return value


def cached_response(client: Any, payload: dict[str, Any], path: Path,
                    cue_ids: list[str], batch_index: int) -> dict[str, Any]:
    """Persist successful HTTP responses before parsing; resume only identical requests."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    if isinstance(record, dict) and record.get("request") == payload and "result" in record:
        return record
    result = client.chat_completions(payload)
    record = {"batch": batch_index, "cue_ids": cue_ids,
              "request": payload, "result": asdict(result)}
    write_json(path, record)
    return record


def run(command: list[str], *, log_path: Path) -> subprocess.CompletedProcess[str]:
    if attempt := RUN_DIRECTORY.get():
        log_path = attempt / "logs" / log_path.name
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", **flags
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + subprocess.list2cmdline(command) + "\n\n"
        + completed.stdout
        + ("\n[stderr]\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"Command failed ({completed.returncode}); see {log_path}")
    return completed


def batches(items: list[Any], size: int) -> Iterable[list[Any]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def parse_numbered_translation(text: str, expected: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    pattern = re.compile(r"^\s*(?:\[\[?|【)?(\d{4})(?:\]\]?|】|[.)、:：])?\s*(.+?)\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            if match.group(1) in found:
                raise ValueError("duplicate translation cue id")
            found[match.group(1)] = match.group(2).strip()
    if set(found) - set(expected):
        raise ValueError("unexpected translation cue id")
    missing = [cue_id for cue_id in expected if cue_id not in found]
    if missing:
        raise ValueError(f"translation response is missing cue ids: {', '.join(missing)}")
    return {cue_id: found[cue_id] for cue_id in expected}


def parse_refinement_json(text: str, expected: list[str]) -> dict[str, str]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    start, end = candidate.find("["), candidate.rfind("]")
    if start < 0 or end < start:
        raise ValueError("refinement response contains no JSON array")
    data = json.loads(candidate[start : end + 1])
    if not isinstance(data, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("translation"), str)
        or not item["translation"].strip() for item in data
    ):
        raise ValueError("invalid refinement items")
    if [item.get("id") for item in data] != expected:
        raise ValueError("refinement ids must match input exactly in order")
    found = {
        str(item["id"]): str(item["translation"]).strip()
        for item in data
        if isinstance(item, dict) and item.get("id") and item.get("translation")
    }
    missing = [cue_id for cue_id in expected if cue_id not in found]
    if missing:
        raise ValueError(f"refinement response is missing cue ids: {', '.join(missing)}")
    return {cue_id: found[cue_id] for cue_id in expected}


def download_video(
    url: str,
    project_dir: Path,
    *,
    yt_dlp: Path,
    ffmpeg: Path,
) -> tuple[Path, dict[str, Any]]:
    source_dir = project_dir / "work" / "01_source"
    source_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        path
        for path in source_dir.glob("source.*")
        if path.stem == "source" and path.suffix not in {".part", ".ytdl", ".json"}
    ]
    if not existing:
        print("[1/7] Downloading YouTube video...", flush=True)
        run(
            [
                str(yt_dlp),
                "--no-playlist",
                "--retries",
                "10",
                "--fragment-retries",
                "10",
                "--socket-timeout",
                "30",
                "--ffmpeg-location",
                str(ffmpeg.parent),
                "-f",
                "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]",
                "--merge-output-format",
                "mp4",
                "-o",
                str(source_dir / "source.%(ext)s"),
                url,
            ],
            log_path=project_dir / "logs" / "01-download.log",
        )
        existing = [
            path
            for path in source_dir.glob("source.*")
            if path.stem == "source" and path.suffix not in {".part", ".ytdl", ".json"}
        ]
    if len(existing) != 1:
        raise RuntimeError(f"expected one downloaded source file, found {len(existing)}")

    metadata_path = source_dir / "metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        completed = run(
            [
                str(yt_dlp),
                "--no-playlist",
                "--skip-download",
                "--print",
                "%(.{id,title,channel,uploader,duration,webpage_url,upload_date,language})j",
                url,
            ],
            log_path=project_dir / "logs" / "01-metadata.log",
        )
        json_lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
        if not json_lines:
            raise RuntimeError("yt-dlp returned no metadata JSON")
        metadata = json.loads(json_lines[-1])
        write_json(metadata_path, metadata)
    if float(metadata.get("duration") or 0) <= 0:
        raise RuntimeError("Source video must have a finite positive duration")
    return existing[0], metadata


def extract_audio(source: Path, project_dir: Path, *, ffmpeg: Path) -> Path:
    audio = project_dir / "work" / "02_audio" / "master.wav"
    state = audio.with_suffix(".state.json")
    key = file_digest(source)
    if not audio.is_file() or read_cached(state, key) != {"complete": True}:
        print("[2/7] Extracting 16 kHz mono audio...", flush=True)
        audio.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(audio.with_name("master.pending.wav")),
            ],
            log_path=project_dir / "logs" / "02-audio.log",
        )
        os.replace(audio.with_name("master.pending.wav"), audio)
        write_json(state, {"key": key, "value": {"complete": True}})
    return audio


def transcribe(audio: Path, project_dir: Path, *, project_root: Path, settings: UserSettings | None = None, source_language: str = "ja", speaker_count: int | None = None) -> dict[str, Any]:
    settings = settings or load_settings(project_root)
    result_path = project_dir / "work" / "03_asr" / "filetrans.json"
    cache_identity = {"audio": file_digest(audio), "model": settings.asr_model, "language": source_language}
    if speaker_count is not None:
        cache_identity['speaker_count'] = speaker_count
    key = fingerprint(cache_identity)
    cached = read_cached(result_path.with_suffix(".cache.json"), key)
    if cached is not None:
        return cached
    print("[3/7] Uploading temporary audio and running Filetrans...", flush=True)
    with runtime_environment(settings):
        client = QwenAudioAsrClient.from_environment()
    task_path = result_path.with_suffix('.task.json')
    task = read_cached(task_path, key)
    if task is not None and not task.get('task_id'):
        raise RuntimeError('ASR submission was interrupted before its task ID was saved. Check provider task history before resubmitting; no automatic duplicate charge was attempted.')
    temporary_url = '' if task else client.upload_temporary_file(audio, model=settings.asr_model)
    if not task:
        write_json(task_path, {'key': key, 'value': {'status': 'submitting'}})
    def save_task(task_id):
        write_json(task_path, {'key': key, 'value': {'task_id': task_id}})
    result = client.recognize_filetrans(
        temporary_url,
        model=settings.asr_model,
        language_hints=asr_hints(source_language),
        diarization_enabled=speaker_count != 1,
        speaker_count=speaker_count if speaker_count and speaker_count >= 2 else None,
        resume_task_id=task.get('task_id') if task else None,
        on_submitted=save_task,
        on_status=lambda status: report_progress(provider_status=status),
    )
    payload = asdict(result)
    write_json(result_path, payload)
    write_json(result_path.with_suffix(".cache.json"), {"key": key, "value": payload})
    return payload


def translate(
    asr: dict[str, Any],
    project_dir: Path,
    *,
    project_root: Path,
    settings: UserSettings | None = None,
    batch_size: int,
    source_language: str = "ja",
    target_language: str = "zh-Hans",
) -> list[dict[str, Any]]:
    settings = settings or load_settings(project_root)
    output_path = project_dir / "work" / "04_translation" / "translation.json"
    key = fingerprint({"asr": asr, "batch_size": batch_size, "model": settings.translation_model, "policy": 2, "source_language": source_language, "target_language": target_language})
    cached = read_cached(output_path.with_suffix(".cache.json"), key)
    if cached is not None:
        return cached
    source_cues = source_cues_from_asr(asr)
    if not source_cues:
        raise ValueError("ASR returned no usable timed speech; inspect the ASR result before exporting")
    print(f"[4/7] Translating {len(source_cues)} timed cues with {settings.translation_model}...", flush=True)
    with runtime_environment(settings):
        client = DashScopeOpenAIClient.from_environment()
    translated: dict[str, str] = {}
    batch_records: list[dict[str, Any]] = []
    report_progress(completed=0,total=len(source_cues),unit='cues')
    for batch_index, group in enumerate(batches(source_cues, batch_size), start=1):
        source = "\n".join(f"[{cue['id']}] {cue['source_text']}" for cue in group)
        payload = qwen_mt_payload(source, model=settings.translation_model, source_language=NAMES[source_language], target_language=NAMES[target_language])
        expected = [cue["id"] for cue in group]
        record = cached_response(client, payload,
            project_dir / "work" / "04_translation" / "batches" / f"{batch_index:03d}.json",
            expected, batch_index)
        try:
            if record["result"].get("finish_reason") == "length":
                raise ValueError("translation was truncated")
            mapped = parse_numbered_translation(record["result"]["content"], expected)
        except ValueError as error:
            # MT can merge adjacent numbered captions. Rebuild this batch one
            # cue at a time; preserve the failed response and cache each repair.
            print(f"  batch {batch_index}: repairing alignment with single-cue requests", flush=True)
            mapped, repairs = recover_translation_batch(client, group,
                project_dir / "work" / "04_translation" / "batches" / f"{batch_index:03d}-recovery", batch_index, model=settings.translation_model, source_language=source_language, target_language=target_language)
            record["recovery"] = {"reason": str(error), "strategy": "single-cue", "records": repairs}
        translated.update(mapped)
        batch_records.append(record)
        write_json(
            project_dir / "work" / "04_translation" / "batches" / f"{batch_index:03d}.json",
            record,
        )
        print(f"  translated batch {batch_index}", flush=True)
        report_progress(completed=len(translated),total=len(source_cues),unit='cues')
    cues = [{**cue, "draft_translation": translated[cue["id"]]} for cue in source_cues]
    write_json(
        output_path,
        {
            "model": settings.translation_model,
            "source_language": source_language,
            "target_language": target_language,
            "batches": batch_records,
            "cues": cues,
        },
    )
    write_json(output_path.with_suffix(".cache.json"), {"key": key, "value": cues})
    return cues


def recover_translation_batch(client: Any, group: list[dict[str, Any]], directory: Path,
                              batch_index: int, *, model: str = "qwen-mt-flash", source_language: str = "ja", target_language: str = "zh-Hans") -> tuple[dict[str, str], list[dict[str, Any]]]:
    mapped: dict[str, str] = {}
    records = []
    for cue in group:
        payload = qwen_mt_payload(cue["source_text"], model=model, source_language=NAMES[source_language], target_language=NAMES[target_language])
        record = cached_response(client, payload, directory / f"{cue['id']}.json", [cue["id"]], batch_index)
        content = record["result"]["content"].strip()
        if not content or record["result"].get("finish_reason") == "length":
            raise ValueError(f"Single-cue recovery failed for {cue['id']}; inspect its response before retrying")
        mapped[cue["id"]] = content
        records.append(record)
    return mapped, records


def refine(
    cues: list[dict[str, Any]],
    project_dir: Path,
    *,
    project_root: Path,
    settings: UserSettings | None = None,
    batch_size: int,
    source_language: str = "ja",
    target_language: str = "zh-Hans",
) -> list[dict[str, Any]]:
    settings = settings or load_settings(project_root)
    output_path = project_dir / "work" / "05_refinement" / "refined.json"
    key = fingerprint({"cues": cues, "batch_size": batch_size, "model": settings.refinement_model, "policy": 1, "source_language": source_language, "target_language": target_language})
    cached = read_cached(output_path.with_suffix(".cache.json"), key)
    if cached is not None:
        return cached
    print(f"[5/7] Refining translations with {settings.refinement_model}...", flush=True)
    with runtime_environment(settings):
        client = DashScopeOpenAIClient.from_environment()
    refined: dict[str, str] = {}
    report_progress(completed=0,total=len(cues),unit='cues')
    batch_records: list[dict[str, Any]] = []
    system = (
        f"你是视频字幕的保守校对员。原文语言：{NAMES[source_language]}（auto 表示按原文判断，可混合语言）。目标语言：{NAMES[target_language]}。"
        "中文目标必须使用简体中文。输入是JSON数组，每项包含id、原文source和初译draft。"
        "只修正错译、直译腔、语序、标点、专名和上下文一致性，不增加或删减信息。"
        "输出严格JSON数组，每项只能包含id和translation；id及顺序必须与输入完全一致，不要Markdown。"
    )
    for batch_index, group in enumerate(batches(cues, batch_size), start=1):
        inputs = [
            {"id": cue["id"], "source": cue["source_text"], "draft": cue["draft_translation"]}
            for cue in group
        ]
        payload = {
            "model": settings.refinement_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(inputs, ensure_ascii=False)},
            ],
            "reasoning_effort": "none",
            "max_completion_tokens": 4096,
        }
        expected = [cue["id"] for cue in group]
        record: dict[str, Any] = {"batch": batch_index, "cue_ids": expected, "request": payload}
        try:
            record = cached_response(client, payload,
                project_dir / "work" / "05_refinement" / "batches" / f"{batch_index:03d}.json",
                expected, batch_index)
            if record["result"].get("finish_reason") == "length":
                raise ValueError("refinement was truncated")
            mapped = parse_refinement_json(record["result"]["content"], expected)
            refined.update(mapped)
        except (DashScopeApiError, ValueError, json.JSONDecodeError) as error:
            for cue in group:
                refined[cue["id"]] = cue["draft_translation"]
            record["fallback"] = "draft_translation"
            record["error"] = str(error)
        batch_records.append(record)
        write_json(
            project_dir / "work" / "05_refinement" / "batches" / f"{batch_index:03d}.json",
            record,
        )
        print(f"  refined batch {batch_index}", flush=True)
        report_progress(completed=len(refined),total=len(cues),unit='cues',fallback_batches=sum('fallback' in item for item in batch_records))
    output_cues = [{**cue, "translation": refined[cue["id"]]} for cue in cues]
    write_json(output_path, {"model": settings.refinement_model, "batches": batch_records, "cues": output_cues})
    write_json(output_path.with_suffix(".cache.json"), {"key": key, "value": output_cues})
    return output_cues


def export_and_mux(
    cues: list[dict[str, Any]],
    source: Path,
    project_dir: Path,
    *,
    ffmpeg: Path,
    stem: str,
    output_dir: Path | None = None,
    speaker_styles: dict | None = None,
    models: dict[str, str] | None = None,
    source_language: str = "ja",
    target_language: str = "zh-Hans",
) -> dict[str, str]:
    models = models or {"asr": DEFAULT_ASR_MODEL, "translation": "qwen-mt-flash", "refinement": "qwen3.8-flash"}
    output_dir = output_dir or project_dir
    stem = safe_project_name(stem)
    output_dir.mkdir(parents=True, exist_ok=True)
    print("[6/7] Exporting source, translated, and bilingual subtitles...", flush=True)
    document = SubtitleDocument(
        source_language="und" if source_language == "auto" else source_language,
        target_language=target_language,
        cues=tuple(
            SubtitleCue(
                cue_id=cue["id"],
                start_ms=cue["start_ms"],
                end_ms=cue["end_ms"],
                source_text=cue["source_text"],
                translation=cue["translation"],
                speaker_id=(str(cue["speaker_id"]) if cue.get("speaker_id") is not None else None),
            )
            for cue in cues
        ),
        metadata={
            **({'speaker_styles':validate_styles(speaker_styles)} if speaker_styles else {}),
            "asr_model": models["asr"],
            "translation_model": models["translation"],
            "refinement_model": models["refinement"],
        },
    )
    font_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    fonts = [font_dir / f"NotoSansCJK{region}-Medium.otf" for region in ("sc", "jp")]
    if any(style.get('font') == 'GenSenRounded2 JP'
           for style in document.metadata.get('speaker_styles', {}).values()):
        fonts.append(font_dir / 'GenSenRounded2JP-M.otf')
    for font in fonts:
        if not font.is_file():
            raise FileNotFoundError(f"Subtitle font missing: {font}; see assets/fonts/README.md")
    # Immutable content versions avoid overwriting a file a player may have cached.
    version = fingerprint({"document": document.to_dict(), "source": file_digest(source),
                           "ass": render_ass(document, mode="bilingual"),
                           "fonts": {font.name: file_digest(font) for font in fonts},
                           "render_policy": 4})[:12]
    versioned_stem = f"{stem}.{version}"
    subtitle_dir = project_dir / "subtitles" / version
    export_dir = project_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    source_paths = export_subtitles(document, subtitle_dir, stem=stem, formats=("json", "srt"), mode="source")
    translated_paths = export_subtitles(document, subtitle_dir, stem=stem, formats=("srt",), mode="translated")
    bilingual_paths = export_subtitles(document, subtitle_dir, stem=stem, formats=("srt", "ass"), mode="bilingual")
    ass_path = next(path for path in bilingual_paths if path.suffix == ".ass")
    final_video = export_dir / f"{versioned_stem}.bilingual.mkv"
    # Static fonts avoid variable-font Thin selection in some libass players.
    attachments = []
    for index, font in enumerate(fonts):
        attachments.extend(["-attach", str(font), f"-metadata:s:t:{index}",
                            "mimetype=application/vnd.ms-opentype",
                            f"-metadata:s:t:{index}", f"filename={font.name}"])
    mux_state = project_dir / "work" / "06_mux" / "state.json"
    signature = {"subtitle_sha256": hashlib.sha256(ass_path.read_bytes()).hexdigest(),
                 "fonts": {font.name: hashlib.sha256(font.read_bytes()).hexdigest() for font in fonts},
                 "source_sha256": file_digest(source)}
    previous = json.loads(mux_state.read_text(encoding="utf-8")) if mux_state.is_file() else {}
    if not final_video.is_file() or previous != signature:
        pending_video = final_video.with_name(final_video.stem + ".pending.mkv")
        print("[7/7] Muxing default bilingual subtitle track into MKV...", flush=True)
        run(
            [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-i", str(ass_path),
                "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
                "-c", "copy", "-c:s", "ass",
                "-metadata:s:s:0", "language=" + {"zh-Hans":"chi","en":"eng","ja":"jpn"}[target_language],
                "-metadata:s:s:0", f"title={NAMES[target_language]} / source",
                "-disposition:s:0", "default",
                *attachments,
                str(pending_video),
            ],
            log_path=project_dir / "logs" / "07-mux.log",
        )
        probe = json.loads(run([
            str(ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")),
            "-v", "error", "-show_streams", "-show_format", "-of", "json", str(pending_video)
        ], log_path=project_dir / "logs" / "07-probe.log").stdout)
        kinds = {stream["codec_type"] for stream in probe["streams"]}
        if not {"video", "subtitle"} <= kinds or float(probe["format"]["duration"]) <= 0:
            raise RuntimeError("mux validation failed; existing video retained")
        attached = {stream.get("tags", {}).get("filename") for stream in probe["streams"]
                    if stream["codec_type"] == "attachment"}
        if not {font.name for font in fonts} <= attached:
            raise RuntimeError("font attachment validation failed; existing video retained")
        os.replace(pending_video, final_video)
        write_json(mux_state, signature)

    # A hard-subbed companion is intentionally generated as well: many Windows
    # players override ASS styles or ignore MKV font attachments. This file is
    # visually deterministic and needs no subtitle settings in the player.
    hard_video = output_dir / f"{versioned_stem}.mp4"
    hard_state = project_dir / "work" / "06_mux" / "hardsub-state.json"
    hard_signature = {**signature, "video_encoder": "libx264-crf18-medium"}
    hard_previous = json.loads(hard_state.read_text(encoding="utf-8")) if hard_state.is_file() else {}
    if not hard_video.is_file() or hard_previous != hard_signature:
        pending_hard = hard_video.with_name(hard_video.stem + ".pending.mp4")
        subtitle_filter = (
            f"subtitles=filename={ffmpeg_filter_path(ass_path)}:"
            f"fontsdir={ffmpeg_filter_path(font_dir)}"
        )
        print("[7/7] Rendering a player-independent hard-subbed MP4...", flush=True)
        run(
            [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-vf", subtitle_filter,
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(pending_hard),
            ],
            log_path=project_dir / "logs" / "07-hardsub.log",
        )
        hard_probe = json.loads(run([
            str(ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")),
            "-v", "error", "-show_streams", "-show_format", "-of", "json", str(pending_hard)
        ], log_path=project_dir / "logs" / "07-hardsub-probe.log").stdout)
        hard_kinds = {stream["codec_type"] for stream in hard_probe["streams"]}
        if "video" not in hard_kinds or "subtitle" in hard_kinds:
            raise RuntimeError("hard-sub validation failed; existing video retained")
        if float(hard_probe["format"]["duration"]) <= 0:
            raise RuntimeError("hard-sub duration validation failed; existing video retained")
        os.replace(pending_hard, hard_video)
        write_json(hard_state, hard_signature)
    # Keep earlier versions for comparison but present only the current MP4 at top level.
    for previous_video in output_dir.glob("*.mp4"):
        if previous_video != hard_video and re.fullmatch(re.escape(stem) + r"\.[0-9a-f]{12}\.mp4", previous_video.name):
            archived = project_dir / "exports" / "previous"
            archived.mkdir(parents=True, exist_ok=True)
            previous_video.replace(archived / previous_video.name)
    paths = (*source_paths, *translated_paths, *bilingual_paths, final_video, hard_video)
    return {path.name: path.relative_to(output_dir).as_posix() for path in paths}


def prepare_source(args: argparse.Namespace, project_dir: Path, *, yt_dlp: Path, ffmpeg: Path, progress=None):
    if args.url:
        if getattr(args, 'acquisition', None) is not None:
            return acquire(args.url, project_dir / 'work' / '01_source', executable=yt_dlp,
                           ffmpeg=ffmpeg, policy=args.acquisition, progress=progress)
        return download_video(args.url, project_dir, yt_dlp=yt_dlp, ffmpeg=ffmpeg)
    original = args.input.resolve()
    destination = project_dir / "work" / "01_source" / ("source" + original.suffix.lower())
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or file_digest(destination) != file_digest(original):
        pending = destination.with_name(destination.name + ".pending")
        total = original.stat().st_size
        copied = 0
        with original.open('rb') as source, pending.open('wb') as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk); copied += len(chunk)
                if progress: progress(copied, total)
        os.replace(pending, destination)
    probe = json.loads(run([str(ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")),
        "-v", "error", "-show_format", "-of", "json", str(destination)],
        log_path=project_dir / "logs" / "01-source.log").stdout)
    return destination, {"title": original.stem, "duration": float(probe["format"]["duration"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--url")
    inputs.add_argument("--input", type=Path, help="local video instead of downloading a URL")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--stem", default="video")
    parser.add_argument("--yt-dlp", type=Path, default=Path(__file__).resolve().parents[1] / ".tools" / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp"))
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--translation-batch-size", type=int, default=12)
    parser.add_argument("--refinement-batch-size", type=int, default=20)
    parser.add_argument('--phase',choices=('all','prepare','export'),default='all')
    parser.add_argument("--source-language", choices=("auto","zh","en","ja"), default="auto")
    parser.add_argument("--target-language", choices=("zh-Hans","en","ja"), default="zh-Hans")
    args = parser.parse_args()
    if args.translation_batch_size <= 0 or args.refinement_batch_size <= 0:
        parser.error("batch sizes must be positive")

    args.stem = safe_project_name(args.stem)
    project = args.project_dir.resolve()
    managed = (project/'intermediates/destination.local.json').exists()
    with lifecycle_lock(project,project.parent) if managed else nullcontext():
        with job_lock(project):
            return execute_job(args)


def execute_job(args: argparse.Namespace) -> int:
    source_language, target_language = validate_languages(getattr(args,"source_language","ja"), getattr(args,"target_language","zh-Hans"))
    project_root = Path(__file__).resolve().parents[1]
    output_dir = args.project_dir.resolve()
    project_dir = output_dir / "intermediates"
    project_dir.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.set(project_dir / 'progress.json')
    if getattr(args,'phase','all') == 'export':
        return export_prepared(args)
    current_settings = load_settings(project_root)
    snapshot_path = project_dir / 'config.snapshot.json'
    if snapshot_path.is_file():
        current_settings = apply_runtime_snapshot(current_settings, json.loads(snapshot_path.read_text(encoding='utf-8')))
    else:
        write_json(snapshot_path, current_settings.runtime_snapshot())
    if not current_settings.api_key:
        raise ValueError('尚未配置阿里云 API Key，请先打开 RinaYaki 设置。')
    models = {"asr": current_settings.asr_model, "translation": current_settings.translation_model,
              "refinement": current_settings.refinement_model}
    if (output_dir / "work").exists():
        raise ValueError("Legacy flat workspace detected; use a new project directory")
    source_identity = args.url if args.url else "file-sha256:" + file_digest(args.input.resolve())
    binding_path = project_dir / "work" / "input-binding.json"
    if binding_path.exists():
        if json.loads(binding_path.read_text(encoding="utf-8"))["url"] != source_identity:
            raise ValueError("project belongs to another URL; use a new project directory")
    else:
        old_project = project_dir / "project.json"
        if old_project.exists() and (json.loads(old_project.read_text(encoding="utf-8")).get("source") or {}).get("url", source_identity) != source_identity:
            raise ValueError("project belongs to another URL; use a new project directory")
        write_json(binding_path, {"url": source_identity})
    started = datetime.now(timezone.utc).isoformat()
    timings: dict[str, float] = {}
    def stage(name: str, function: Any, *values: Any, **options: Any) -> Any:
        begin = time.perf_counter()
        report_progress(status='running', stage=name, run_id=run_id, completed=0, total=None)
        try:
            return function(*values, **options)
        finally:
            timings[name] = round(time.perf_counter() - begin, 4)
            write_json(run_dir / "timings.json",
                       {"started_at": started, "stage_wall_seconds_including_cache": timings})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = project_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    RUN_DIRECTORY.set(run_dir)
    write_json(run_dir / "run.json", {"status": "running", "started_at": started,
               "input": source_identity, "translation_batch_size": args.translation_batch_size,
               "refinement_batch_size": args.refinement_batch_size, "models": models})
    try:
        source, metadata = stage("download", prepare_source,
            args,
            project_dir,
            yt_dlp=args.yt_dlp.resolve(),
            ffmpeg=args.ffmpeg.resolve(),
            progress=lambda completed,total: report_progress(status='running',stage='download',completed=completed,total=total),
        )
        audio = stage("audio", extract_audio, source, project_dir, ffmpeg=args.ffmpeg.resolve())
        asr = stage("asr", transcribe, audio, project_dir, project_root=project_root,
                    settings=current_settings, source_language=source_language, speaker_count=getattr(args,'speaker_count',None))
        translated = stage("translation", translate,
            asr,
            project_dir,
            project_root=project_root,
            settings=current_settings,
            batch_size=args.translation_batch_size, source_language=source_language, target_language=target_language,
        )
        refined = stage("refinement", refine,
            translated,
            project_dir,
            project_root=project_root,
            settings=current_settings,
            batch_size=args.refinement_batch_size, source_language=source_language, target_language=target_language,
        )
        # Provider receipts in the project are the durable audit trail. Replay
        # them into the central daily ledger so a transient local write failure
        # cannot leave a successfully completed job looking like zero usage.
        reconcile_project_billing(project_dir, current_settings)
        if getattr(args,'phase','all') == 'prepare':
            prepared = {'schema_version':1, 'source':source.relative_to(output_dir).as_posix(),
                        'audio':audio.relative_to(output_dir).as_posix(), 'metadata':metadata,
                        'source_language':source_language, 'target_language':target_language,
                        'speaker_count':getattr(args,'speaker_count',None),
                        'models':models, 'cues':refined, 'speakers':speaker_samples(refined), 'stem':args.stem}
            prepared['key'] = fingerprint(prepared)
            write_json(project_dir / 'prepared.json',prepared)
            report_progress(status='awaiting_style',stage='prepared',completed=len(refined),total=len(refined))
            write_json(run_dir / 'run.json',{'status':'awaiting_style','started_at':started,'prepared_key':prepared['key']})
            return 0
        outputs = stage("export_and_mux", export_and_mux,
            refined,
            source,
            project_dir,
            ffmpeg=args.ffmpeg.resolve(),
            stem=args.stem,
            output_dir=output_dir, models=models, source_language=source_language, target_language=target_language,
        )
    except Exception as error:
        report_progress(status='failed', error=str(error), run_id=run_id)
        write_json(
            run_dir / "run.json",
            {"status": "failed", "started_at": started, "error": str(error)},
        )
        raise
    finally:
        archive_attempt(project_dir, run_dir)
        RUN_DIRECTORY.set(None)
        PROGRESS_FILE.set(None)

    project = {
        "schema_version": 1,
        "project_id": output_dir.name,
        "created_at": (json.loads((project_dir / "project.json").read_text(encoding="utf-8")).get("created_at", started)
                       if (project_dir / "project.json").exists() else started),
        "source": {
            "site": "web" if args.url else "local",
            "url": metadata.get("webpage_url") or source_identity,
            "video_id": metadata.get("id"),
            "title": metadata.get("title"),
            "channel": metadata.get("channel") or metadata.get("uploader"),
            "duration_seconds": metadata.get("duration"),
        },
    }
    pipeline = {
        "schema_version": 2,
        "path_base": "job_root",
        "status": "complete",
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stage_wall_seconds_including_cache": timings,
        "refinement_fallback_batches": sum("fallback" in item for item in json.loads(
            (project_dir / "work/05_refinement/refined.json").read_text(encoding="utf-8"))["batches"]),
        "models": models,
        "current": {
            "source_video": source.relative_to(output_dir).as_posix(),
            "audio": audio.relative_to(output_dir).as_posix(),
            "asr": "intermediates/work/03_asr/filetrans.json",
            "translation": "intermediates/work/04_translation/translation.json",
            "refinement": "intermediates/work/05_refinement/refined.json",
            "deliverables": outputs,
        },
    }
    write_json(project_dir / "project.json", project)
    write_json(project_dir / "pipeline.json", pipeline)
    write_json(run_dir / "run.json", pipeline)
    write_json(project_dir / 'progress.json', {'status': 'complete', 'run_id': run_id})
    print(json.dumps({"project_dir": str(output_dir), "outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


def export_prepared(args):
    """Export a reviewed preparation without constructing any cloud client."""
    output_dir = args.project_dir.resolve()
    details = output_dir / 'intermediates'
    run_dir = details / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-export-' + uuid.uuid4().hex[:8])
    RUN_DIRECTORY.set(run_dir)
    run_dir.mkdir(parents=True)
    report_progress(status='running',stage='export_and_mux',completed=0,total=None)
    try:
        prepared = json.loads((details/'prepared.json').read_text(encoding='utf-8'))
        key = prepared.pop('key')
        if fingerprint(prepared) != key:
            raise ValueError('Prepared result changed; prepare the job again before exporting')
        styles = json.loads((details/'styles.json').read_text(encoding='utf-8'))
        if styles.get('prepared_key') != key:
            raise ValueError('Styles belong to another preparation; reopen the style editor')
        source = (output_dir/prepared['source']).resolve()
        if not source.is_relative_to(output_dir):
            raise ValueError('Source path is outside the job')
        outputs = export_and_mux(prepared['cues'],source,details,ffmpeg=args.ffmpeg.resolve(),
            stem=args.stem,output_dir=output_dir,speaker_styles=validate_styles(styles['speakers']),
            models=prepared.get('models'), source_language=prepared.get('source_language','ja'), target_language=prepared.get('target_language','zh-Hans'))
        result = {'status':'complete','path_base':'job_root','prepared_key':key,'outputs':outputs}
        write_json(details/'pipeline.json',result)
        write_json(run_dir/'run.json',result)
        report_progress(status='complete')
        return 0
    except Exception as error:
        write_json(run_dir/'run.json',{'status':'failed','error':str(error)})
        report_progress(status='failed',error=str(error))
        raise
    finally:
        archive_attempt(details,run_dir)
        RUN_DIRECTORY.set(None)
        PROGRESS_FILE.set(None)


if __name__ == "__main__":
    raise SystemExit(main())
