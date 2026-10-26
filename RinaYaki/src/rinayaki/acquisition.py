"""Video acquisition with explicit quality and app-owned login sessions.

RinaYaki never reads a daily browser profile and never asks users to import a
cookie file. An open WebView may provide one short-lived internal snapshot;
otherwise yt-dlp reads only RinaYaki's isolated WebView2 profile.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import queue
import threading
import time

from rinayaki.site_skills import (
    diagnose_error, extractor_args as site_extractor_args, inspect_capabilities,
    quality_choices,
)


def options(value=None) -> dict:
    """Normalize the non-secret policy persisted with a job.

    Unknown keys are ignored so jobs created by the withdrawn login prototype
    still open, but authentication data is never read or forwarded.
    """
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError('视频下载设置无效。')
    quality = value.get('quality', 'auto')
    if not isinstance(quality, str) or not re.fullmatch(
            r'auto|[1-9][0-9]{1,4}p|bili-q[1-9][0-9]{0,3}', quality):
        raise ValueError('视频下载设置无效。')
    session = value.get('session', 'anonymous')
    if session not in {'anonymous', 'app'}:
        raise ValueError('视频下载设置无效。')
    return {'quality': quality, 'session': session}


def session_args(source: str, session: str = 'anonymous', cookie_file=None) -> list[str]:
    if cookie_file is not None:
        from rinayaki.web_session.model import validate_snapshot
        return ['--cookies', str(validate_snapshot(source, cookie_file))]
    if session != 'app':
        return []
    from rinayaki.web_session.model import browser_cookie_spec, has_persisted_session
    if not has_persisted_session(source):
        raise ValueError('登录会话不存在，请重新登录。')
    return ['--cookies-from-browser', browser_cookie_spec(source)]


def extractor_args(source: str = '', *, session: str = 'anonymous', cookie_file=None) -> list[str]:
    args = ['--ignore-config', '--no-playlist', '--no-cache-dir',
            '--socket-timeout', '20', '--retries', '2']
    runtimes = {name for name in ('node',) if shutil.which(name)}
    return [*args, *site_extractor_args(source, runtimes),
            *session_args(source, session, cookie_file)]


def safe_error(stderr: str, source: str = '') -> str:
    return diagnose_error(source, stderr)


def checked_run(command: list[str], timeout: int, source: str = '', progress=None):
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    if progress is not None:
        return _checked_run_progress(command, timeout, source, progress, flags)
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout, **flags)
    except subprocess.TimeoutExpired:
        raise ValueError('读取视频超时，请稍后重试。') from None
    except OSError:
        raise ValueError('视频下载组件不可用，请检查安装。') from None
    if result.returncode:
        raise ValueError(safe_error(result.stderr, source))
    return result


def _checked_run_progress(command, timeout, source, progress, flags):
    """Read yt-dlp progress without ever persisting its potentially secret output."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', bufsize=1, **flags)
    except OSError:
        raise ValueError('视频下载组件不可用，请检查安装。') from None
    messages: queue.Queue[str | None] = queue.Queue()
    def read():
        assert process.stdout is not None
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)
    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + timeout
    output: list[str] = []
    output_size = 0
    finished = False
    while not finished:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill(); process.wait()
            raise ValueError('读取视频超时，请稍后重试。')
        try:
            line = messages.get(timeout=min(.25, remaining))
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        if line is None:
            finished = True
            continue
        # Keep only a bounded in-memory tail for site-specific error diagnosis.
        output.append(line); output_size += len(line)
        while output_size > 256 * 1024 and output:
            output_size -= len(output.pop(0))
        percent = _progress_value(line)
        if percent is not None:
            progress(percent, 100.0)
    try:
        code = process.wait(timeout=max(.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        process.kill(); process.wait()
        raise ValueError('读取视频超时，请稍后重试。') from None
    result = subprocess.CompletedProcess(command, code, '', ''.join(output))
    if code:
        raise ValueError(safe_error(result.stderr, source))
    progress(100.0, 100.0)
    return result


def _progress_value(line: str):
    match = re.search(r'rinayaki-progress:\s*([0-9]+(?:\.[0-9]+)?)%', line)
    return None if match is None else min(100.0, max(0.0, float(match.group(1))))


def extract(value: str, executable: Path, *, session: str = 'anonymous', cookie_file=None) -> dict:
    result = checked_run([str(executable), *extractor_args(
        value, session=session, cookie_file=cookie_file), '--skip-download',
                          '--dump-single-json', '--', value], 90, value)
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise ValueError('视频解析结果无效，请稍后重试。') from None
    if not isinstance(data, dict) or data.get('_type') in {'playlist', 'multi_video'} or data.get('entries') is not None or data.get('is_live'):
        raise ValueError('请提供单个已结束的视频，而不是首页或视频列表。')
    if float(data.get('duration') or 0) <= 0:
        raise ValueError('无法确定视频时长。')
    if data.get('is_preview') or data.get('is_trailer'):
        raise ValueError('当前只能访问试看内容。')
    data['_rinayaki_capabilities'] = inspect_capabilities(
        value, data, result.stderr)
    return data


def qualities(data: dict) -> list[dict]:
    available = [{'id': 'auto', 'label': '自动', 'available': True},
                 *quality_choices(data)]
    locked = [item for item in (
        data.get('_rinayaki_capabilities', {}).get('locked_qualities') or [])
        if (isinstance(item, dict) and item.get('available') is False
            and isinstance(item.get('id'), str) and isinstance(item.get('label'), str))]
    return [*available, *locked]


def selector(quality: str) -> str:
    quality = options({'quality': quality})['quality']
    if quality == 'auto':
        return 'bv*+ba/b'
    if quality.startswith('bili-q'):
        suffix = f'[quality={int(quality.removeprefix("bili-q"))}]'
        return f'bv*{suffix}+ba/b{suffix}'
    edge = int(quality[:-1])
    # Platforms name vertical and horizontal video by their short edge. Check
    # height first for the common landscape case, then width for vertical video.
    return (f'bv*[height={edge}]+ba/bv*[width={edge}]+ba/'
            f'b[height={edge}]/b[width={edge}]')


def cache_key(source: str, policy: dict) -> str:
    return hashlib.sha256(json.dumps([source, options(policy)], sort_keys=True).encode()).hexdigest()[:20]


def acquire(source: str, directory: Path, *, executable: Path, ffmpeg: Path, policy: dict, progress=None) -> tuple[Path, dict]:
    policy = options(policy)
    parent = directory.resolve()
    directory = directory / cache_key(source, policy)
    if not directory.resolve().is_relative_to(parent):
        raise ValueError('视频缓存路径无效。')
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / 'complete.json'
    if marker.is_file() and marker.stat().st_size < 65536:
        try:
            saved = json.loads(marker.read_text(encoding='utf-8'))
            target = directory / saved['file']
            if (target.resolve().parent == directory.resolve() and target.is_file()
                    and target.stat().st_size == saved.get('size') and isinstance(saved['metadata'], dict)
                    and float(saved['metadata'].get('duration') or 0) > 0):
                return target, saved['metadata']
        except (OSError, ValueError, TypeError, KeyError):
            pass
    data = extract(source, executable, session=policy['session'])
    if policy['quality'] not in {
            item['id'] for item in qualities(data) if item.get('available', True)}:
        raise ValueError('所选画质已不可用，请重新预览后选择。')
    # Raw extractor stderr may contain signed URLs or account details: do not log it.
    checked_run([str(executable), *extractor_args(source, session=policy['session']),
        '--newline', '--progress', '--progress-template', 'download:rinayaki-progress:%(progress._percent_str)s',
        '--check-formats', '-f', selector(policy['quality']), '--ffmpeg-location', str(ffmpeg.parent),
        '--merge-output-format', 'mkv', '-o', str(directory / 'source.%(ext)s'), '--', source], 7200, source, progress)
    files = [path for path in directory.glob('source.*') if path.suffix.lower() in {'.mp4', '.mkv', '.webm', '.flv', '.mov', '.avi', '.ts'}]
    if len(files) != 1:
        raise ValueError('下载结果不完整，请重新预览后重试。')
    metadata = {key: data.get(key) for key in ('id', 'title', 'duration', 'language', 'upload_date')}
    pending = marker.with_suffix('.tmp')
    pending.write_text(json.dumps({'file': files[0].name, 'size': files[0].stat().st_size, 'metadata': metadata}, ensure_ascii=False), encoding='utf-8')
    pending.replace(marker)
    return files[0], metadata
