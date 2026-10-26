"""Job isolation, content fingerprints and per-attempt audit records."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

RUN_DIRECTORY: ContextVar[Path | None] = ContextVar('run_directory', default=None)
PROGRESS_FILE: ContextVar[Path | None] = ContextVar('progress_file', default=None)


def report_progress(**values):
    path = PROGRESS_FILE.get()
    if path is None:
        return
    try:
        current = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        current = {}
    if 'stage' in values and values['stage'] != current.get('stage'):
        current = {'status': 'running', 'stage_started_at': time.time()}
    current.update(values, updated_at=time.time())
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        pending.write_text(json.dumps(current, ensure_ascii=False),encoding='utf-8')
        os.replace(pending,path)
    finally:
        pending.unlink(missing_ok=True)


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_cached(path: Path, key: str):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value.get('value') if isinstance(value, dict) and value.get('key') == key else None


@contextmanager
def job_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.running.lock'
    stream = lock.open('a+b')
    stream.seek(0, 2)
    if stream.tell() == 0:
        stream.write(b'0')
        stream.flush()
    stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            for attempt in range(6):
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if attempt == 5:
                        raise
                    time.sleep(.05)  # Windows may finish releasing a killed process's handles asynchronously.
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('This job is already running.') from None
    try:
        yield
    finally:
        # Keep the inode stable: deleting it creates a race with waiting processes.
        stream.close()  # OS releases the lock even when this process crashes.


def archive_attempt(details: Path, run_dir: Path) -> None:
    # Preserve text/API artifacts, not another copy of large source video/audio.
    for name in ('03_asr', '04_translation', '05_refinement', '06_mux'):
        source = details / 'work' / name
        if source.exists():
            shutil.copytree(source, run_dir / 'artifacts' / name, dirs_exist_ok=True)
