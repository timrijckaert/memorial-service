# tests/test_stitching.py
from pathlib import Path
from PIL import Image
from src.images.stitching import stitch_pair


def _make_image(path: Path, width: int, height: int, color: str) -> Path:
    """Create a solid-color test image."""
    img = Image.new("RGB", (width, height), color)
    img.save(path, "JPEG")
    return path


def test_stitch_same_height(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 120, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    assert result.size == (220, 200)


def test_stitch_different_heights_scales_shorter(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 80, 100, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    # Back was 80x100, scaled to height 200 -> width becomes 160
    assert result.size == (260, 200)


def test_stitch_front_shorter_than_back(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 100, "red")
    back = _make_image(tmp_path / "back.jpeg", 120, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    # Front was 100x100, scaled to height 200 -> width becomes 200
    assert result.size == (320, 200)


def test_stitch_outputs_jpeg(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 100, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    assert result.format == "JPEG"


def test_stitch_pixel_content_is_correct(tmp_path):
    """Verify front pixels are on the left and back pixels are on the right."""
    front = _make_image(tmp_path / "front.jpeg", 20, 20, "red")
    back = _make_image(tmp_path / "back.jpeg", 20, 20, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    assert result.size == (40, 20)

    # Sample center of left half (front) — should be red-ish
    left_pixel = result.getpixel((10, 10))
    assert left_pixel[0] > 150  # R channel high
    assert left_pixel[2] < 100  # B channel low

    # Sample center of right half (back) — should be blue-ish
    right_pixel = result.getpixel((30, 10))
    assert right_pixel[0] < 100  # R channel low
    assert right_pixel[2] > 150  # B channel high
