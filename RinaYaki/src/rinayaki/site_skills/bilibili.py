"""Bilibili-only capability hints.

yt-dlp compares the site's declared ``support_formats`` with formats actually
returned to the anonymous session and emits one bounded warning for the gap.
This adapter owns that version-sensitive interpretation so it cannot spread
through the downloader or UI.
"""
from __future__ import annotations

import re

from .base import SiteSkill, host, short_edge, usable_video_formats


_MISSING = re.compile(r'Format\(s\)\s+(.+?)\s+are missing;', re.IGNORECASE)
_QUALITY_LABELS = {
    127: '8K 超高清',
    126: '杜比视界',
    125: 'HDR 真彩',
    120: '4K 超清',
    116: '1080P 60帧',
    112: '1080P 高码率',
    80: '1080P 高清',
    74: '720P 60帧',
    64: '720P 准高清',
    32: '480P 清晰',
    16: '360P 流畅',
}


def display_label(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()[:32]


class BilibiliSkill(SiteSkill):
    site = 'bilibili'

    @classmethod
    def matches(cls, source: str) -> bool:
        return host(source) in {'bilibili.com', 'm.bilibili.com', 'b23.tv'}

    @classmethod
    def quality_choices(cls, data: dict) -> list[dict]:
        choices = {}
        for item in usable_video_formats(data):
            quality = item.get('quality')
            if not isinstance(quality, (int, float)) or quality != int(quality):
                continue
            quality = int(quality)
            label = _QUALITY_LABELS.get(quality) or display_label(
                item.get('format_note') or item.get('format') or '')
            if '\ufffd' in label or not re.match(
                    r'^(?:\d{3,4}P|[48]K|HDR|杜比)(?:\s|$)', label, re.IGNORECASE):
                edge = short_edge(item)
                label = f'{edge}P' if edge else ''
            if label:
                choices.setdefault(quality, label)
        if not choices:
            return super().quality_choices(data)
        return [{'id': f'bili-q{quality}', 'label': label, 'available': True}
                for quality, label in sorted(choices.items(), reverse=True)]

    @classmethod
    def inspect(cls, source: str, data: dict, diagnostics: str) -> dict:
        result = super().inspect(source, data, diagnostics)
        found = _MISSING.search(diagnostics or '')
        if not found:
            return result
        seen = set()
        for position, raw in enumerate(found.group(1).split(',')):
            name = raw.strip()
            label = display_label(name)
            if not name or label in seen:
                continue
            seen.add(label)
            result['locked_qualities'].append({
                'id': f'locked:bilibili:{position}',
                'label': label,
                'available': False,
                'requirement': 'premium',
                'message': f'“{name}”需要哔哩哔哩大会员；登录后会再次确认账号权限。',
                'action': {'kind': 'open_source', 'label': '打开登录窗口'},
            })
        return result

    @classmethod
    def diagnose_error(cls, diagnostics: str, source: str = '') -> str:
        text = diagnostics.lower()
        if "keyerror('bvid')" in text or 'extractor error has occurred' in text:
            return '哔哩哔哩解析暂时失败，请稍后重试。'
        return super().diagnose_error(diagnostics, source)
