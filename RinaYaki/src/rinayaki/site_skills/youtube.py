"""YouTube capability boundary."""
from .base import SiteSkill, host


class YouTubeSkill(SiteSkill):
    site = 'youtube'

    @classmethod
    def matches(cls, source: str) -> bool:
        return host(source) in {'youtube.com', 'm.youtube.com', 'youtu.be'}

    @classmethod
    def extractor_args(cls, runtimes: set[str]) -> list[str]:
        return ['--js-runtimes', 'node'] if 'node' in runtimes else []

    @classmethod
    def diagnose_error(cls, diagnostics: str, source: str = '') -> str:
        text = diagnostics.lower()
        if 'sign in to confirm' in text or "you're not a bot" in text:
            return 'YouTube 需要登录验证。'
        if any(word in text for word in (
                'connectionreset', 'connection was reset', 'connection aborted',
                'unable to connect to proxy', 'remote end closed connection')):
            return 'YouTube 连接失败，请检查网络代理。'
        return super().diagnose_error(diagnostics, source)
