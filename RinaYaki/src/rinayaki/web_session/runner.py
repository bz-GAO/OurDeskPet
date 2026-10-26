"""WebView2 host. No cookie or authorization data leaves this process yet."""
from __future__ import annotations

from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import os
import sys
import tempfile
import time
from urllib.parse import urlsplit

from .model import SessionTarget, profile_directory, session_target, snapshot_directory


@contextmanager
def session_lock(site: str):
    """Keep one WebView2 session per site/profile."""
    root = profile_directory(site).parent
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / f'{site}.lock'
    lock_path.touch(exist_ok=True)
    handle = lock_path.open('r+b')
    acquired = False
    try:
        if os.name == 'nt':
            import msvcrt
            if lock_path.stat().st_size == 0:
                handle.seek(0)
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError('该站点的登录窗口已经打开。') from error
            acquired = True
        yield
    finally:
        if os.name == 'nt' and acquired:
            import msvcrt
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()


def _expiry(value) -> int:
    if not value:
        return 0
    try:
        return max(0, int(parsedate_to_datetime(str(value)).timestamp()))
    except (TypeError, ValueError, OverflowError):
        return 0


def write_cookie_snapshot(target: SessionTarget, cookies) -> Path:
    """Write a bounded, short-lived Netscape jar without logging its values."""
    runtime = snapshot_directory()
    runtime.mkdir(parents=True, exist_ok=True)
    host = (urlsplit(target.url).hostname or '').lower()
    rows = ['# Netscape HTTP Cookie File']
    for cookie in cookies or ():
        for morsel in getattr(cookie, 'values', lambda: ())():
            name, value = morsel.key, morsel.value
            domain = (morsel['domain'] or host).lower()
            plain_domain = domain.lstrip('.')
            include_subdomains = domain.startswith('.')
            if (not plain_domain or (host != plain_domain
                    and not host.endswith('.' + plain_domain))):
                continue
            fields = (name, value, domain, morsel['path'] or '/')
            if any('\t' in str(item) or '\r' in str(item) or '\n' in str(item)
                   for item in fields):
                continue
            if morsel['httponly']:
                domain = '#HttpOnly_' + domain
            rows.append('\t'.join((
                domain,
                'TRUE' if include_subdomains else 'FALSE',
                morsel['path'] or '/',
                'TRUE' if morsel['secure'] else 'FALSE',
                str(_expiry(morsel['expires'])),
                name,
                value,
            )))
    handle = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', prefix=f'{target.site}-',
        suffix='.cookies.txt', dir=runtime, delete=False)
    try:
        handle.write('\r\n'.join(rows) + '\r\n')
    finally:
        handle.close()
    try:
        os.chmod(handle.name, 0o600)
    except OSError:
        pass
    return Path(handle.name)


def run_window(target: SessionTarget, *, storage_path: Path | None = None,
               hidden: bool = False, auto_close_seconds: float | None = None) -> None:
    try:
        import webview
    except ImportError as error:
        raise RuntimeError('网页登录组件尚未安装。') from error
    profile = storage_path or profile_directory(target.site)
    profile.mkdir(parents=True, exist_ok=True)
    window = webview.create_window(
        f'RinaYaki 登录 · {target.title}', target.url,
        width=1100, height=760, min_size=(760, 520), hidden=hidden,
        text_select=True, zoomable=True,
    )

    snapshots = set()

    def serve_requests():
        if auto_close_seconds is not None:
            time.sleep(auto_close_seconds)
            window.destroy()
            return
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get('action') == 'close':
                    print('{"ok":true}', flush=True)
                    window.destroy()
                    return
                requested = session_target(request.get('source', ''))
                if request.get('action') != 'snapshot' or requested.site != target.site:
                    raise ValueError('登录会话请求无效。')
                path = write_cookie_snapshot(requested, window.get_cookies())
                snapshots.add(path)
                response = {'ok': True, 'path': str(path)}
            except Exception:
                response = {'ok': False, 'error': '无法读取登录会话。'}
            try:
                print(json.dumps(response, ensure_ascii=False), flush=True)
            except (BrokenPipeError, OSError):
                return

    try:
        with session_lock(target.site):
            webview.start(
                serve_requests,
                gui='edgechromium', private_mode=False, storage_path=str(profile),
                debug=False,
            )
    finally:
        for path in snapshots:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
