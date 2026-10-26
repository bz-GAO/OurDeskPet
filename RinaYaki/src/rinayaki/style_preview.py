"""Pixel-accurate local preview for the bundled subtitle fonts."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .styling import FONT_FILES, normalize_color


BACKGROUND = '#24242A'


def _text_width(draw, text, font, stroke_width):
    left, _top, right, _bottom = draw.textbbox(
        (0, 0), text, font=font, stroke_width=stroke_width)
    return right - left


def _wrap_text(draw, text, font, maximum_width, stroke_width, maximum_lines=2):
    text = ' '.join(str(text).split()) or '字幕预览'
    lines = []
    remaining = text
    while remaining and len(lines) < maximum_lines:
        if _text_width(draw, remaining, font, stroke_width) <= maximum_width:
            lines.append(remaining)
            remaining = ''
            break
        best = 1
        for index in range(2, len(remaining) + 1):
            if _text_width(draw, remaining[:index], font, stroke_width) > maximum_width:
                break
            best = index
        candidate = remaining[:best]
        break_at = max(candidate.rfind(' '), candidate.rfind('、'), candidate.rfind('。'))
        if break_at >= max(1, best // 2):
            best = break_at + 1
        lines.append(remaining[:best].strip())
        remaining = remaining[best:].strip()
    if remaining and lines:
        last = lines[-1]
        while last and _text_width(draw, last + '…', font, stroke_width) > maximum_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + '…'
    return lines


def render_style_preview(text, *, font_name, fonts_directory, outline_color,
                         width=720, height=96, font_size=30):
    """Render the same bundled font and white/outline pairing used by ASS export."""
    if font_name not in FONT_FILES:
        raise ValueError('请选择受支持的字幕字体。')
    fonts_directory = Path(fonts_directory).resolve()
    font_path = (fonts_directory / FONT_FILES[font_name]).resolve()
    if not font_path.is_relative_to(fonts_directory) or not font_path.is_file():
        raise FileNotFoundError('字幕字体文件缺失。')
    color = normalize_color(outline_color)
    image = Image.new('RGB', (int(width), int(height)), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), int(font_size))
    stroke_width = 2
    lines = _wrap_text(draw, text, font, image.width - 36, stroke_width)
    boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
             for line in lines]
    line_height = max((bottom - top for _left, top, _right, bottom in boxes), default=32)
    gap = 7
    total_height = line_height * len(lines) + gap * max(0, len(lines) - 1)
    y = (image.height - total_height) // 2
    for line, (left, top, right, bottom) in zip(lines, boxes):
        text_width = right - left
        x = (image.width - text_width) // 2 - left
        draw.text((x, y - top), line, font=font, fill='white',
                  stroke_width=stroke_width, stroke_fill=color)
        y += line_height + gap
    return image


def render_live_style_preview(source, translation, *, display_mode, font_name,
                              fonts_directory, outline_color, font_size, width=720):
    """Render the live window's white text, outline, and bilingual size split."""
    if display_mode not in {'source', 'translation', 'bilingual'}:
        raise ValueError('显示模式无效。')
    if font_name not in FONT_FILES:
        raise ValueError('请选择受支持的字幕字体。')
    root = Path(fonts_directory).resolve()
    path = (root / FONT_FILES[font_name]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError('字幕字体文件缺失。')
    color = normalize_color(outline_color)
    rows = []
    if display_mode != 'translation':
        rows.append((source, font_size if display_mode == 'source' else max(10,font_size-7)))
    if display_mode != 'source':
        rows.append((translation,font_size))
    fonts = [ImageFont.truetype(str(path), max(12,round(points * 4 / 3))) for _text,points in rows]
    scratch = ImageDraw.Draw(Image.new('RGB',(1,1)))
    boxes = [scratch.textbbox((0,0),text,font=font,stroke_width=2) for (text,_),font in zip(rows,fonts)]
    heights = [bottom-top for _left,top,_right,bottom in boxes]
    height = max(96, 24 + sum(heights) + 12 * max(0,len(rows)-1))
    image = Image.new('RGB',(width,height),'#101418')
    draw = ImageDraw.Draw(image)
    y = (height - sum(heights) - 12 * max(0,len(rows)-1)) // 2
    for (text,_points),font,(left,top,right,_bottom),line_height in zip(rows,fonts,boxes,heights):
        x = (width - (right-left)) // 2 - left
        draw.text((x,y-top),text,font=font,fill='white',stroke_width=2,stroke_fill=color)
        y += line_height + 12
    return image
