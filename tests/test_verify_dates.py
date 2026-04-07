# tests/test_verify_dates.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw

from src.extraction.date_verification import verify_dates


def _make_image_with_text(tmp_path: Path, text: str, filename: str = "card.jpeg") -> Path:
    """Create a simple image with text for testing."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), text, fill="black")
    path = tmp_path / filename
    img.save(path, "JPEG")
    return path


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_corrects_misread_year(mock_data, tmp_path):
    """When LLM reads a different year than OCR, the text file is updated."""
    image_path = _make_image_with_text(tmp_path, "overleden 27 Februari 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "27", "Februari", "1944,"],
        "left": [10, 120, 150, 250],
        "top": [40, 40, 40, 40],
        "width": [100, 20, 80, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 86],
    }
    backend.generate_vision.return_value = "1941"

    corrections = verify_dates(image_path, text_path, backend, conflicts_dir)

    assert corrections == ["1944 -> 1941"]
    assert "1941" in text_path.read_text()
    assert "1944" not in text_path.read_text()


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_saves_conflict_image(mock_data, tmp_path):
    """When OCR and LLM disagree, a crop image is saved for manual review."""
    image_path = _make_image_with_text(tmp_path, "1944", filename="card_back.jpeg")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("den 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["1944,"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [86],
    }
    backend.generate_vision.return_value = "1941"

    verify_dates(image_path, text_path, backend, conflicts_dir)

    assert conflicts_dir.exists()
    conflict_files = list(conflicts_dir.glob("*.png"))
    assert len(conflict_files) == 1
    assert "ocr1944" in conflict_files[0].name
    assert "llm1941" in conflict_files[0].name


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_correction_when_matching(mock_data, tmp_path):
    """When LLM and OCR agree, text is unchanged."""
    image_path = _make_image_with_text(tmp_path, "geboren 15 Juni 1852")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("geboren 15 Juni 1852")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["geboren", "15", "Juni", "1852"],
        "left": [10, 100, 130, 200],
        "top": [40, 40, 40, 40],
        "width": [80, 20, 40, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 68],
    }
    backend.generate_vision.return_value = "1852"

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "geboren 15 Juni 1852"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_rejects_llm_year_outside_range(mock_data, tmp_path):
    """When LLM returns a year outside 1800-1950, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1926")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1926")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "1926"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }
    backend.generate_vision.return_value = "2026"

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "overleden 1926"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_years_skips_llm(mock_data, tmp_path):
    """When no year-like words are found, no LLM calls are made."""
    image_path = _make_image_with_text(tmp_path, "no dates here")
    text_path = tmp_path / "card_front.txt"
    text_path.write_text("no dates here")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["no", "dates", "here"],
        "left": [10, 30, 70],
        "top": [40, 40, 40],
        "width": [15, 35, 30],
        "height": [20, 20, 20],
        "conf": [95, 95, 95],
    }

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_ignores_invalid_llm_response(mock_data, tmp_path):
    """When LLM returns non-year text, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1944")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "1944"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }
    backend.generate_vision.return_value = "The year shown is 1941"

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "overleden 1944"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_stray_crop_files(mock_data, tmp_path):
    """No stray crop files are left after verification."""
    image_path = _make_image_with_text(tmp_path, "1913")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("1913")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["1913"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [95],
    }
    backend.generate_vision.return_value = "1913"

    verify_dates(image_path, text_path, backend)

    crop_files = list(tmp_path.glob("_crop_*.png"))
    assert crop_files == []
