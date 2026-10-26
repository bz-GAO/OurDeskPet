"""Launch WebView2 in an isolated child process."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from .model import session_target, validate_snapshot


@dataclass(slots=True)
class WebSessionProcess:
    site: str
    process: subprocess.Popen
    _responses: queue.Queue
    _requests: threading.Lock

    def snapshot_cookies(self, source: str, timeout: float = 10) -> Path:
        """Ask the child to create one short-lived cookie file for yt-dlp."""
        if self.process.poll() is not None or not self.process.stdin:
            raise RuntimeError('登录窗口已关闭。')
        with self._requests:
            self.process.stdin.write(json.dumps(
                {'action': 'snapshot', 'source': session_target(source).url},
                ensure_ascii=False) + '\n')
            self.process.stdin.flush()
            try:
                response = self._responses.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError('无法读取登录会话。') from None
        if not response.get('ok'):
            raise RuntimeError(response.get('error') or '无法读取登录会话。')
        return validate_snapshot(source, response['path'])

    def close(self, timeout: float = 5) -> None:
        if self.process.poll() is not None:
            return
        try:
            with self._requests:
                if not self.process.stdin:
                    raise OSError
                self.process.stdin.write('{"action":"close"}\n')
                self.process.stdin.flush()
                self._responses.get(timeout=timeout)
            self.process.wait(timeout=timeout)
        except (OSError, queue.Empty, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                self.process.terminate()

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


def _responses(process: subprocess.Popen) -> queue.Queue:
    responses = queue.Queue()

    def read():
        if not process.stdout:
            return
        for line in process.stdout:
            try:
                value = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                responses.put(value)

    threading.Thread(target=read, daemon=True).start()
    return responses


def can_open_session(value: str | None = None) -> bool:
    if os.name != 'nt' or importlib.util.find_spec('webview') is None:
        return False
    if value is None:
        return True
    try:
        session_target(value)
        return True
    except ValueError:
        return False


def launch_session(value: str) -> WebSessionProcess:
    target = session_target(value)
    if not can_open_session():
        raise RuntimeError('网页登录组件尚未安装。')
    repo_root = Path(__file__).resolve().parents[3]
    source_root = repo_root / 'src'
    environment = os.environ.copy()
    existing = environment.get('PYTHONPATH', '')
    environment['PYTHONPATH'] = str(source_root) + (os.pathsep + existing if existing else '')
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    process = subprocess.Popen(
        [sys.executable, '-m', 'rinayaki.web_session', '--source', target.url],
        cwd=repo_root,
        env=environment,
        creationflags=flags,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding='utf-8',
    )
    return WebSessionProcess(
        site=target.site, process=process, _responses=_responses(process),
        _requests=threading.Lock())


def launch_detached_session(value: str) -> dict:
    """Open the Yaki-owned login window for callers without a long-lived pipe.

    RinaDesk invokes its bridge once per action, so it cannot own a
    ``WebSessionProcess``.  The detached child still uses this package, this
    project's isolated profile and the same site lock; closing its window
    flushes the profile for the next preview.
    """
    target = session_target(value)
    if not can_open_session():
        raise RuntimeError('网页登录组件尚未安装。')
    repo_root = Path(__file__).resolve().parents[3]
    source_root = repo_root / 'src'
    environment = os.environ.copy()
    existing = environment.get('PYTHONPATH', '')
    environment['PYTHONPATH'] = str(source_root) + (os.pathsep + existing if existing else '')
    executable = Path(sys.executable)
    if os.name == 'nt':
        pythonw = executable.with_name('pythonw.exe')
        if pythonw.is_file():
            executable = pythonw
        flags = (getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                 | getattr(subprocess, 'DETACHED_PROCESS', 0)
                 | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        flags = 0
    process = subprocess.Popen(
        [str(executable), '-m', 'rinayaki.web_session', '--source', target.url],
        cwd=repo_root,
        env=environment,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return {'site': target.site, 'title': target.title, 'process_id': process.pid}
