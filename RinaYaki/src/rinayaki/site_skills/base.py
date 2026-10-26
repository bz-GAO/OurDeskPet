"""Shared, non-secret video capability model."""
from __future__ import annotations

from urllib.parse import urlparse


ACCESS_MESSAGES = {
    'needs_auth': '需要登录后确认观看权限。',
    'premium_only': '需要会员权限。',
    'subscriber_only': '需要订阅当前频道。',
    'private': '这是非公开视频。',
}


def host(source: str) -> str:
    return (urlparse(source).hostname or '').lower().removeprefix('www.')


def base_capabilities(data: dict) -> dict:
    access = data.get('availability')
    if access not in {'public', 'unlisted', 'needs_auth', 'premium_only',
                      'subscriber_only', 'private'}:
        access = 'unknown'
    return {
        'site': 'generic',
        'access': access,
        'message': ACCESS_MESSAGES.get(access),
        'locked_qualities': [],
    }


def usable_video_formats(data: dict):
    for item in data.get('formats') or []:
        if (isinstance(item, dict) and item.get('vcodec') not in (None, 'none')
                and item.get('url') and not item.get('has_drm')):
            yield item


def short_edge(item: dict) -> int | None:
    dimensions = [value for value in (item.get('width'), item.get('height'))
                  if isinstance(value, (int, float)) and 10 <= value < 100000
                  and value == int(value)]
    return int(min(dimensions)) if dimensions else None


class SiteSkill:
    site = 'generic'

    @classmethod
    def matches(cls, source: str) -> bool:
        return False

    @classmethod
    def inspect(cls, source: str, data: dict, diagnostics: str) -> dict:
        result = base_capabilities(data)
        result['site'] = cls.site
        return result

    @classmethod
    def quality_choices(cls, data: dict) -> list[dict]:
        resolutions = {value for item in usable_video_formats(data)
                       if (value := short_edge(item)) is not None}
        return [{'id': f'{value}p', 'label': f'{value}P', 'available': True}
                for value in sorted(resolutions, reverse=True)]

    @classmethod
    def extractor_args(cls, runtimes: set[str]) -> list[str]:
        return []

    @classmethod
    def diagnose_error(cls, diagnostics: str, source: str = '') -> str:
        text = diagnostics.lower()
        site = host(source)
        label = site if site else '此视频'
        if any(word in text for word in (
                'login', 'sign in', 'private', 'members', 'subscription',
                'ppv', 'premium', 'cookie', '403', '401')):
            return f'{label} 需要登录或订阅权限。'
        if any(word in text for word in (
                'timed out', 'connectionreset', 'connection was reset',
                'connection aborted', 'unable to connect to proxy',
                'remote end closed connection')):
            return '视频站点连接失败，请稍后重试。'
        if 'format' in text:
            return '所选画质暂不可用，请重新预览后选择。'
        return '无法读取视频，请检查链接或网络。'
