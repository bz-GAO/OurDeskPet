"""Mellow-Fan/OpenRec capability boundary."""
from .base import SiteSkill, host


class MellowFanSkill(SiteSkill):
    site = 'mellowfan'

    @classmethod
    def matches(cls, source: str) -> bool:
        return host(source) in {'mellow-fan.com', 'openrec.tv'}

    @classmethod
    def diagnose_error(cls, diagnostics: str, source: str = '') -> str:
        text = diagnostics.lower()
        if any(word in text for word in ('subscription', 'subscriber', 'ppv', 'premium', 'login')):
            return 'Mellow-Fan 需要登录或订阅权限。'
        if 'http error 404' in text:
            return 'Mellow-Fan 当前无法交给下载器解析。'
        if any(word in text for word in (
                'connectionreset', 'connection was reset', 'connection aborted',
                'recv failure', 'remote end closed connection')):
            return 'Mellow-Fan 连接失败，请稍后重试。'
        return super().diagnose_error(diagnostics, source)
