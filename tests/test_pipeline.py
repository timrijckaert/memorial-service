# tests/test_pipeline.py
"""Tests for the extraction pipeline orchestration."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.extraction.pipeline import extract_one, ExtractionResult


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_calls_steps_in_order(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Pipeline calls OCR, date verify, and interpret in order."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_backend = MagicMock()
    mock_verify.return_value = []

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_backend, "system", "template",
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back", "date_verify", "llm_extract"]
    assert mock_ocr.call_count == 2
    assert mock_verify.call_count == 2
    assert mock_interpret.call_count == 1
    assert result.ocr_done is True
    assert result.interpreted is True
    assert result.errors == []


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_stops_on_ocr_front_failure(mock_ocr, tmp_path):
    """If OCR front fails, the pipeline stops and reports the error."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_ocr.side_effect = RuntimeError("tesseract crashed")

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
    )

    assert result.ocr_done is False
    assert len(result.errors) == 1
    assert "OCR front" in result.errors[0]


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_skips_llm_without_backend(mock_ocr, tmp_path):
    """Without a backend, date verify and interpret are skipped."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back"]
    assert result.ocr_done is True
    assert result.interpreted is False


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_reports_date_corrections(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Date corrections are counted and recorded."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_backend = MagicMock()
    mock_verify.side_effect = [["1944 -> 1941"], []]

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_backend, "system", "template",
    )

    assert result.verify_corrections == 1
    assert len(result.date_fixes) == 1


def test_extraction_result_defaults():
    """ExtractionResult has sensible defaults."""
    result = ExtractionResult(front_name="test.jpeg")

    assert result.front_name == "test.jpeg"
    assert result.ocr_done is False
    assert result.verify_corrections == 0
    assert result.interpreted is False
    assert result.errors == []
    assert result.date_fixes == []
