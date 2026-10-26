from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .subtitles import SUPPORTED_FORMATS, export_subtitles, load_subtitle_document
from .workspace import create_project


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _find_tool(name: str) -> str | None:
    executable = f"{name}.exe" if sys.platform == "win32" else name
    project_root = _project_root()
    private_candidates = {
        "ffmpeg": project_root / ".tools" / "ffmpeg" / executable,
        "ffprobe": project_root / ".tools" / "ffmpeg" / executable,
        "yt-dlp": project_root / ".tools" / executable,
    }
    private = private_candidates.get(name)
    if private and private.is_file():
        return str(private)
    return shutil.which(name)


def _default_workspace() -> Path:
    return Path.cwd() / "workspaces"


def _doctor() -> int:
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 11),
            "value": sys.version.split()[0],
        },
        "ffmpeg": {"ok": _find_tool("ffmpeg") is not None, "value": _find_tool("ffmpeg")},
        "ffprobe": {"ok": _find_tool("ffprobe") is not None, "value": _find_tool("ffprobe")},
        "yt-dlp": {"ok": _find_tool("yt-dlp") is not None, "value": _find_tool("yt-dlp")},
    }
    print(json.dumps({"rinayaki": __version__, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if checks["python"]["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rinayaki", description="Japanese-first subtitle pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="check the local runtime without downloading anything")

    init_parser = subparsers.add_parser("init", help="create an offline subtitle project")
    init_parser.add_argument("name", help="project name")
    init_parser.add_argument("--root", type=Path, default=_default_workspace())

    export_parser = subparsers.add_parser(
        "export-subtitles", help="export canonical or ASR JSON to subtitle files"
    )
    export_parser.add_argument("input", type=Path)
    export_parser.add_argument("--output-dir", type=Path, required=True)
    export_parser.add_argument("--stem")
    export_parser.add_argument(
        "--formats", nargs="+", choices=SUPPORTED_FORMATS, default=list(SUPPORTED_FORMATS)
    )
    export_parser.add_argument(
        "--mode", choices=("source", "translated", "bilingual"), default="source"
    )
    export_parser.add_argument("--font", default="Noto Sans CJK SC Medium")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "init":
        try:
            project_dir = create_project(args.root, args.name)
        except (FileExistsError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(project_dir)
        return 0
    if args.command == "export-subtitles":
        try:
            document = load_subtitle_document(args.input)
            paths = export_subtitles(
                document,
                args.output_dir,
                stem=args.stem or args.input.stem,
                formats=args.formats,
                mode=args.mode,
                font_name=args.font,
            )
        except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(json.dumps([str(path) for path in paths], ensure_ascii=False, indent=2))
        return 0
    return 2
