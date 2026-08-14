"""Classic meme rendering with Pillow: white block caps, heavy black outline."""
import io
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

from common import config

# Anton (SIL Open Font License) ships beside the handler. It is an open,
# redistributable stand-in for Impact with the same condensed-bold look.
_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "Anton-Regular.ttf")

_MARGIN_RATIO = 0.035
_MAX_TEXT_HEIGHT_RATIO = 0.34  # per caption block, top or bottom


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except Exception:
        # Last-resort so rendering degrades instead of failing the request.
        return ImageFont.load_default()


def _line_width(draw: ImageDraw.ImageDraw, text: str, font, stroke: int = 0) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return right - left


def _line_height(font) -> int:
    """Full line box from font metrics.

    Deliberately not the bbox of a sample string: a string without descenders
    ("AY") measures short, which makes a multi-line block underestimate its own
    height and run off the bottom of the image. draw.text() positions text by
    the ascender line, so ascent + descent is the height that actually matches
    how it will be drawn.
    """
    ascent, descent = font.getmetrics()
    return ascent + descent


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Greedy word wrap; falls back to hard character splits for long words."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _line_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    exploded: list[str] = []
    for line in lines:
        if _line_width(draw, line, font) <= max_width or len(line) <= 1:
            exploded.append(line)
            continue
        chunk = ""
        for char in line:
            if _line_width(draw, chunk + char, font) <= max_width:
                chunk += char
            else:
                if chunk:
                    exploded.append(chunk)
                chunk = char
        if chunk:
            exploded.append(chunk)
    return exploded


def _stroke_for(font) -> int:
    return max(2, int(font.size * 0.09))


def _fit_block(draw, text, img_w, img_h):
    """Shrink the font until the wrapped block fits its allotted band."""
    max_height = int(img_h * _MAX_TEXT_HEIGHT_RATIO)
    size = max(18, int(img_h * 0.115))

    while True:
        font = _load_font(size)
        stroke = _stroke_for(font)
        # The stroke grows the text on both sides, so the usable width for
        # wrapping has to account for it or long lines overflow horizontally.
        max_width = int(img_w * (1 - 2 * _MARGIN_RATIO)) - 2 * stroke
        lines = _wrap(draw, text, font, max_width)
        line_h = _line_height(font)
        spacing = int(line_h * 0.06)
        total = len(lines) * line_h + max(0, len(lines) - 1) * spacing + 2 * stroke

        if total <= max_height or size <= 14:
            return font, lines, line_h, spacing, stroke
        size = max(14, int(size * 0.9))


def _draw_block(draw, text, img_w, img_h, position: str) -> None:
    if not text.strip():
        return
    font, lines, line_h, spacing, stroke = _fit_block(draw, text.upper(), img_w, img_h)
    if not lines:
        return

    block_h = len(lines) * line_h + max(0, len(lines) - 1) * spacing
    margin = int(img_h * _MARGIN_RATIO)

    # draw.text() anchors on the ascender line, and the stroke extends `stroke`
    # pixels past the glyphs in every direction, so both ends inset by it.
    if position == "top":
        y = margin + stroke
    else:
        y = img_h - margin - stroke - block_h

    for line in lines:
        line_w = _line_width(draw, line, font, stroke)
        x = (img_w - line_w) / 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0),
        )
        y += line_h + spacing


def render_meme(image_bytes: bytes, top_text: str, bottom_text: str) -> bytes:
    """Overlay the caption on the image and return JPEG bytes."""
    with Image.open(io.BytesIO(image_bytes)) as src:
        img = ImageOps.exif_transpose(src)  # respect phone photo orientation
        img = img.convert("RGB")

        if max(img.size) > config.OUTPUT_MAX_EDGE:
            img.thumbnail((config.OUTPUT_MAX_EDGE, config.OUTPUT_MAX_EDGE), Image.LANCZOS)

        draw = ImageDraw.Draw(img)
        width, height = img.size
        _draw_block(draw, top_text, width, height, "top")
        _draw_block(draw, bottom_text, width, height, "bottom")

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88, optimize=True, progressive=True)
        return out.getvalue()
