"""Image byte helpers shared by the tests.

Separate from ``conftest.py`` so test modules can import them by name; pytest
puts the test directory on ``sys.path``, but conftest is not importable as a
module from a test module.
"""

import io

from PIL import Image


def png_bytes(w, h, color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(w, h, color=(0, 0, 255)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def image_size(data):
    """``(width, height, format)`` of encoded image bytes."""
    with Image.open(io.BytesIO(data)) as im:
        return im.size[0], im.size[1], im.format


def pixel_at(data, x=5, y=5):
    """One RGB pixel from encoded image bytes."""
    with Image.open(io.BytesIO(data)) as im:
        return im.convert("RGB").getpixel((x, y))