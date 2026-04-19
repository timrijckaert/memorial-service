# tests/test_pipeline.py
"""Tests for the 2-stage extraction pipeline."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from src.extraction.pipeline import extract_one, ExtractionResult


def _make_test_image(path: Path) -> Path:
    """Create a minimal test image."""
    img = Image.new("RGB", (100, 50), "white")
    img.save(path, "JPEG")
    return path


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_calls_vision_then_text(mock_interpret, tmp_path):
    """Pipeline calls vision read then text structuring in order."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Dominicus Meganck geboren 1813"

    steps = []
    result = extract_one(
        front, back, json_dir,
        mock_backend, "system prompt", "vision prompt",
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["vision_read", "text_extract"]
    assert mock_backend.generate_vision.call_count == 1
    assert mock_interpret.call_count == 1
    assert result.interpreted is True
    assert result.errors == []


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_sends_both_images(mock_interpret, tmp_path):
    """Vision model receives both front and back images."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"

    extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    call_args = mock_backend.generate_vision.call_args
    images = call_args.kwargs.get("images") or call_args.args[1]
    assert len(images) == 2


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_single_sided_card(mock_interpret, tmp_path):
    """Single-sided cards send only one image."""
    front = _make_test_image(tmp_path / "card.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"

    result = extract_one(front, None, json_dir, mock_backend, "sys", "vis")

    call_args = mock_backend.generate_vision.call_args
    images = call_args.kwargs.get("images") or call_args.args[1]
    assert len(images) == 1
    assert result.interpreted is True


def test_extract_one_skips_without_backend(tmp_path):
    """Without a backend, nothing runs."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    steps = []
    result = extract_one(
        front, back, json_dir,
        None, None, None,
        on_step=lambda s: steps.append(s),
    )

    assert steps == []
    assert result.interpreted is False


def test_extract_one_reports_vision_error(tmp_path):
    """If vision read fails, the error is captured and text extract is skipped."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.side_effect = RuntimeError("model crashed")

    result = extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    assert len(result.errors) == 1
    assert "vision" in result.errors[0].lower()
    assert result.interpreted is False


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_reports_interpret_error(mock_interpret, tmp_path):
    """If text structuring fails, the error is captured."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"
    mock_interpret.side_effect = ValueError("bad json")

    result = extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    assert len(result.errors) == 1
    assert "interpret" in result.errors[0].lower()
    assert result.interpreted is False


def test_extraction_result_defaults():
    """ExtractionResult has sensible defaults."""
    result = ExtractionResult(front_name="test.jpeg")

    assert result.front_name == "test.jpeg"
    assert result.interpreted is False
    assert result.errors == []
