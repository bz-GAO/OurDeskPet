"""Deterministic input normalization and metadata-only preview."""
from pathlib import Path
import json
import re
import subprocess
from urllib.parse import urlparse, parse_qs, urlencode
from rinayaki.acquisition import extract, options, qualities


def local_thumbnail(source: str, duration: float, root: Path) -> bytes | None:
    """Sample a frame without changing the source or leaving temporary files."""
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
    for position in (min(10, duration * .1), 0):
        try:
            result = subprocess.run([str(root/'.tools/ffmpeg/ffmpeg.exe'),'-v','error',
                '-ss',str(position),'-i',source,'-map','0:v:0','-frames:v','1',
                '-vf','scale=640:360:force_original_aspect_ratio=decrease',
                '-f','image2pipe','-vcodec','mjpeg','pipe:1'],capture_output=True,timeout=20,**flags)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def normalize_input(value: str) -> tuple[str, str]:
    value = value.strip().strip('"')
    if not value:
        raise ValueError('请输入链接、视频号或选择本地视频。')
    if Path(value).is_file():
        return 'local', str(Path(value).resolve())
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', value):
        return 'web', 'https://www.bilibili.com/video/' + value
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return 'web', 'https://www.youtube.com/watch?v=' + value
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password:
        raise ValueError('无法识别输入，请使用完整视频链接或选择本地文件。')
    if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}:
        parts = parsed.path.strip('/').split('/')
        vid = parts[0] if host == 'youtu.be' else (parse_qs(parsed.query).get('v', [''])[0] if parsed.path == '/watch' else (parts[1] if len(parts) == 2 and parts[0] in {'shorts','live','embed'} else ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise ValueError('请提供单个 YouTube 视频，而不是频道或播放列表。')
        return 'web', 'https://www.youtube.com/watch?v=' + vid
    if host in {'bilibili.com','www.bilibili.com','m.bilibili.com','b23.tv'}:
        if host != 'b23.tv' and not re.match(r'^/video/(BV[0-9A-Za-z]{10}|av\d+)(?:/|$)', parsed.path):
            raise ValueError('请提供单个哔哩哔哩视频。')
        if host != 'b23.tv':
            part = parse_qs(parsed.query).get('p', [''])[0]
            query = '?' + urlencode({'p': part}) if part.isdecimal() and int(part) > 0 else ''
            return 'web', 'https://www.bilibili.com' + parsed.path.rstrip('/') + query
        return 'web', value
    if not host or parsed.path in {'', '/'}:
        raise ValueError('请提供单个视频页面，而不是网站首页。')
    return 'web', value


def preview(value: str, root: Path, *, cookie_file=None,
            use_app_session: bool = False) -> dict:
    kind, source = normalize_input(value)
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
    if kind == 'local':
        result = subprocess.run([str(root/'.tools/ffmpeg/ffprobe.exe'), '-v','error','-show_streams','-show_format','-of','json',source], capture_output=True, text=True, encoding='utf-8', timeout=30, **flags)
    else:
        from rinayaki.web_session.model import has_persisted_session
        session = ('app' if cookie_file or (
            use_app_session and has_persisted_session(source)) else 'anonymous')
        data = extract(source, root/'.tools/yt-dlp.exe', session=session,
                       cookie_file=cookie_file)
    if kind == 'local':
        if result.returncode:
            raise ValueError('无法读取视频文件。')
        data = json.loads(result.stdout)
    if kind == 'local':
        if not any(s.get('codec_type') == 'video' for s in data.get('streams', [])):
            raise ValueError('所选文件没有视频画面。')
        data = {'title': Path(source).name, 'duration': data.get('format',{}).get('duration')}
    if data.get('_type') in {'playlist','multi_video'} or data.get('is_live'):
        raise ValueError('目前只处理单个已结束的视频。')
    if float(data.get('duration') or 0) <= 0:
        raise ValueError('无法确定视频时长。')
    return {'kind':kind, 'source':source, 'title':data.get('title') or source,
            'duration':float(data['duration']), 'thumbnail':data.get('thumbnail'),
            'acquisition': options({'session': session}) if kind == 'web' else None,
            'qualities': qualities(data) if kind == 'web' else [],
            'capabilities': data.get('_rinayaki_capabilities') if kind == 'web' else None}
