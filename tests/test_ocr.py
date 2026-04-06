# tests/test_ocr.py
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.merge import extract_text

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract not installed",
)


def _make_text_image(path: Path, text: str) -> Path:
    """Create a white image with black text drawn on it."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=40)
    draw.text((10, 25), text, fill="black", font=font)
    img.save(path, "JPEG")
    return path


def test_extract_text_creates_output_file(tmp_path):
    image_path = _make_text_image(tmp_path / "card.jpeg", "Hello World")
    output_path = tmp_path / "card_front.txt"

    extract_text(image_path, output_path)

    assert output_path.exists()


def test_extract_text_produces_content(tmp_path):
    image_path = _make_text_image(tmp_path / "card.jpeg", "Hello World")
    output_path = tmp_path / "card_front.txt"

    extract_text(image_path, output_path)

    content = output_path.read_text()
    assert len(content) > 0


def test_extract_text_blank_image_creates_file(tmp_path):
    """A blank image with no text should still create the output file."""
    img = Image.new("RGB", (200, 100), "white")
    image_path = tmp_path / "blank.jpeg"
    img.save(image_path, "JPEG")
    output_path = tmp_path / "blank_front.txt"

    extract_text(image_path, output_path)

    assert output_path.exists()
