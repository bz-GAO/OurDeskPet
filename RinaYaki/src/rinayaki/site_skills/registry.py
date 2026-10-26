"""Route one URL to one isolated site capability skill."""
from .base import SiteSkill
from .bilibili import BilibiliSkill
from .mellowfan import MellowFanSkill
from .youtube import YouTubeSkill


SITE_SKILLS = (BilibiliSkill, YouTubeSkill, MellowFanSkill)


def skill_for(source: str) -> type[SiteSkill]:
    return next((item for item in SITE_SKILLS if item.matches(source)), SiteSkill)


def inspect_capabilities(source: str, data: dict, diagnostics: str = '') -> dict:
    return skill_for(source).inspect(source, data, diagnostics)


def extractor_args(source: str, runtimes: set[str]) -> list[str]:
    return skill_for(source).extractor_args(runtimes)


def diagnose_error(source: str, diagnostics: str) -> str:
    return skill_for(source).diagnose_error(diagnostics, source)


def quality_choices(data: dict) -> list[dict]:
    site = (data.get('_rinayaki_capabilities') or {}).get('site')
    skill = next((item for item in SITE_SKILLS if item.site == site), SiteSkill)
    return skill.quality_choices(data)
