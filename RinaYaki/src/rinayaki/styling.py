"""Validated subtitle styles shared by the editor and export pipeline."""
import re
import os
from pathlib import Path

PRESETS = {
    '默认': '#000000',
    '璃奈': '#616D87',
    '步梦': '#E55073',
    '霞': '#E1CF04',
    '雫': '#01B7ED',
    '果林': '#485EC6',
    '爱': '#FF5800',
    '彼方': '#A664A0',
    '雪菜': '#D81C2F',
    '艾玛': '#84C36E',
    '栞子': '#37B484',
    '米娅': '#A7A69F',
    '岚珠': '#E69595',
}
DEFAULT_FONT = 'Noto Sans CJK SC Medium'
GENSEN_FONT = 'GenSenRounded2 JP'
FONTS = {
    '默认 · Noto Sans CJK': DEFAULT_FONT,
    '源泉圆体 · GenSen Rounded': GENSEN_FONT,
}
FONT_FILES = {
    DEFAULT_FONT: 'NotoSansCJKsc-Medium.otf',
    GENSEN_FONT: 'GenSenRounded2JP-M.otf',
}


def register_private_fonts(fonts_directory):
    """Make the bundled faces available to Tk without installing system fonts."""
    if os.name != 'nt':
        return
    import ctypes
    root = Path(fonts_directory).resolve()
    for name in FONT_FILES.values():
        path = (root / name).resolve()
        if path.is_relative_to(root) and path.is_file():
            ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)


def tk_family(font_name):
    # Windows GDI exposes this face with the weight suffix in its family name.
    return 'GenSenRounded2 JP M' if font_name == GENSEN_FONT else font_name


def normalize_color(value):
    value = str(value).strip()
    if not re.fullmatch(r'#?[0-9a-fA-F]{6}',value):
        raise ValueError('请输入六位颜色代码，例如 #616D87。')
    return '#' + value.lstrip('#').upper()


def validate_styles(value):
    if not isinstance(value,dict):
        raise ValueError('Invalid speaker styles')
    result = {}
    for speaker, style in value.items():
        font = style.get('font',DEFAULT_FONT) if isinstance(style,dict) else None
        if font not in FONTS.values():
            raise ValueError('请选择受支持的字幕字体。')
        result[str(speaker)] = {
            'color': normalize_color(style.get('color','#000000')),
            'font': font,
        }
    return result


def ass_color(value):
    color = normalize_color(value)[1:]
    return '&H' + color[4:6] + color[2:4] + color[0:2] + '&'


def speaker_key(cue):
    value = cue.get('speaker_id')
    return str(value) if value is not None else 'unknown'


def speaker_samples(cues):
    groups = {}
    for cue in cues:
        key = speaker_key(cue)
        previous = groups.get(key)
        length = min(6000, cue['end_ms']-cue['start_ms'])
        if previous is None or length > previous['length_ms']:
            groups[key] = {'start_ms':cue['start_ms'], 'length_ms':length,
                           'text':cue['source_text'], 'translation':cue.get('translation','')}
    return groups
