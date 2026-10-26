"""Validated targets and private per-site storage for login windows."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from rinayaki.settings import config_home
from rinayaki.site_skills.registry import skill_for
from rinayaki.video_input import normalize_input


SITE_TITLES = {
    'bilibili': '哔哩哔哩',
    'youtube': 'YouTube',
    'mellowfan': 'Mellow-Fan',
}
_SITE_KEY = re.compile(r'(?:bilibili|youtube|mellowfan|site-[0-9a-f]{16})\Z')


@dataclass(frozen=True, slots=True)
class SessionTarget:
    site: str
    title: str
    url: str


def session_target(value: str) -> SessionTarget:
    kind, source = normalize_input(value)
    if kind != 'web':
        raise ValueError('本地视频不需要网页登录。')
    parsed = urlsplit(source)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('登录窗口只接受 HTTPS 视频页面。')
    skill = skill_for(source)
    if skill.site in SITE_TITLES:
        site, title = skill.site, SITE_TITLES[skill.site]
    else:
        hostname = (parsed.hostname or '').lower().removeprefix('www.')
        if not hostname:
            raise ValueError('无法识别登录网站。')
        site = 'site-' + hashlib.sha256(hostname.encode('idna')).hexdigest()[:16]
        title = hostname
    # Fragments are page-local state and never belong in the child command line.
    clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    return SessionTarget(site=site, title=title, url=clean)


def profile_directory(site: str) -> Path:
    if not isinstance(site, str) or not _SITE_KEY.fullmatch(site):
        raise ValueError('登录站点无效。')
    root = (config_home() / 'web_sessions').resolve(strict=False)
    path = (root / site).resolve(strict=False)
    if path.parent != root:
        raise ValueError('登录数据目录无效。')
    return path


def chromium_profile_directory(source: str) -> Path:
    """Return the WebView2 Chromium root without inspecting stored values."""
    return profile_directory(session_target(source).site) / 'EBWebView'


def has_persisted_session(source: str) -> bool:
    """Whether the app profile has a cookie store (not whether it is logged in)."""
    root = chromium_profile_directory(source)
    return any(path.is_file() for path in (
        root / 'Default' / 'Network' / 'Cookies',
        root / 'Default' / 'Cookies',
    ))


def browser_cookie_spec(source: str) -> str:
    """yt-dlp browser spec for the isolated WebView2 profile."""
    return 'edge:' + str(chromium_profile_directory(source))


def snapshot_directory() -> Path:
    return (config_home() / 'web_sessions' / 'runtime').resolve(strict=False)


def validate_snapshot(source: str, value: str | Path) -> Path:
    target = session_target(source)
    root = snapshot_directory()
    path = Path(value).resolve(strict=False)
    if (path.parent != root or not path.name.startswith(target.site + '-')
            or not path.name.endswith('.cookies.txt') or not path.is_file()):
        raise ValueError('登录会话临时文件无效。')
    return path
