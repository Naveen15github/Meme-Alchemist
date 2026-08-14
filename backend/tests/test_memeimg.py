import io

import pytest
from PIL import Image

from conftest import make_image_bytes
from generate import memeimg


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_renders_a_valid_jpeg():
    out = memeimg.render_meme(make_image_bytes(), "TOP LINE", "BOTTOM LINE")
    img = _open(out)
    assert img.format == "JPEG"
    assert img.size == (640, 480)


def test_downscales_oversized_images():
    out = memeimg.render_meme(make_image_bytes((3000, 2000)), "A", "B")
    assert max(_open(out).size) == 1080


def test_small_images_are_not_upscaled():
    out = memeimg.render_meme(make_image_bytes((200, 150)), "A", "B")
    assert _open(out).size == (200, 150)


def test_accepts_png_input_and_emits_jpeg():
    out = memeimg.render_meme(make_image_bytes(fmt="PNG"), "PNG", "INPUT")
    assert _open(out).format == "JPEG"


@pytest.mark.parametrize("top,bottom", [
    ("ONLY TOP", ""),
    ("", "ONLY BOTTOM"),
    ("", ""),
    ("A VERY LONG CAPTION THAT HAS TO WRAP ACROSS SEVERAL LINES TO FIT", "SHORT"),
    ("SUPERCALIFRAGILISTICEXPIALIDOCIOUSNESSSSSSSSSSSSSSSS", "B"),
])
def test_handles_caption_edge_cases(top, bottom):
    out = memeimg.render_meme(make_image_bytes(), top, bottom)
    assert _open(out).format == "JPEG"


def test_actually_draws_something():
    """A flat source image plus white caption text must change some pixels."""
    plain = make_image_bytes()
    captioned = memeimg.render_meme(plain, "HELLO", "WORLD")

    original = _open(plain).convert("RGB")
    result = _open(captioned).convert("RGB")
    assert original.tobytes() != result.tobytes()

    # White text should be present after captioning and absent before.
    assert any(px == (255, 255, 255) for px in result.getdata())


def test_narrow_and_wide_aspect_ratios():
    for size in [(400, 1200), (1200, 400)]:
        out = memeimg.render_meme(make_image_bytes(size), "WIDE", "TALL")
        assert _open(out).format == "JPEG"


def _has_white_in_rows(img, y0, y1):
    px = img.load()
    return any(px[x, y] == (255, 255, 255) for y in range(y0, y1) for x in range(0, img.width, 3))


@pytest.mark.parametrize("bottom", [
    "FORCED TO BE PHOTOGENIC",
    "A LONGER PUNCHLINE THAT WILL DEFINITELY WRAP ONTO TWO LINES",
    "GYQPJ",  # all descenders - the case that exposed the clipping bug
])
def test_bottom_caption_is_not_clipped(bottom):
    """Regression: line height came from the bbox of a descender-free string,
    so multi-line bottom blocks ran off the edge of the image."""
    out = memeimg.render_meme(make_image_bytes((900, 675)), "TOP", bottom)
    img = _open(out).convert("RGB")

    # Text must be drawn above the very last rows, i.e. fully inside the frame.
    assert _has_white_in_rows(img, img.height - 90, img.height - 12)
    assert not _has_white_in_rows(img, img.height - 3, img.height)


def test_top_caption_is_not_clipped():
    out = memeimg.render_meme(make_image_bytes((900, 675)), "GYQPJ TOP LINE", "B")
    img = _open(out).convert("RGB")

    assert _has_white_in_rows(img, 12, 90)
    assert not _has_white_in_rows(img, 0, 3)


def test_long_caption_stays_within_horizontal_bounds():
    out = memeimg.render_meme(make_image_bytes((900, 675)), "WWWWWWWWWWWWWWWWWWWWWWWWWWWW", "B")
    img = _open(out).convert("RGB")
    px = img.load()

    # Nothing should be painted in the outermost columns.
    assert not any(px[x, y] == (255, 255, 255)
                   for x in (0, 1, img.width - 2, img.width - 1)
                   for y in range(0, img.height, 3))
