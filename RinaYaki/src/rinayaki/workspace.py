from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIRECTORIES = (
    "intermediates/work",
    "intermediates/subtitles",
    "intermediates/exports",
    "intermediates/runs",
)


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def safe_project_name(value: str) -> str:
    normalized = "".join(
        "-" if character in '<>:"/\\|?*' or ord(character) < 32 else character
        for character in value.strip()
    ).rstrip(" .")
    if not normalized:
        raise ValueError("project name must contain at least one safe character")
    if normalized.split('.')[0].upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"project name is reserved by Windows: {normalized}")
    return normalized


def create_project(root: Path, name: str) -> Path:
    project_name = safe_project_name(name)
    project_dir = root.expanduser().resolve() / project_name
    if project_dir.exists():
        raise FileExistsError(f"project already exists: {project_dir}")

    project_dir.mkdir(parents=True)
    for directory in PROJECT_DIRECTORIES:
        (project_dir / directory).mkdir(parents=True)

    manifest = {
        "schema_version": 1,
        "project_id": project_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": None,
        "mode": "offline",
        "status": "created",
        "stages": {},
    }
    (project_dir / "intermediates" / "project.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return project_dir
