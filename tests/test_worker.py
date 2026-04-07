# tests/test_worker.py
"""Tests for the ExtractionWorker async two-stage pipeline."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.web.worker import ExtractionWorker, ExtractionStatus, CardError, CardProgress


def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict with in_flight."""
    status = ExtractionStatus(
        status="running",
        in_flight=[CardProgress("card1", "ocr"), CardProgress("card2", "date_verify")],
        done=["card0"],
        errors=[CardError("card3", "failed")],
        queue=["card4"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["in_flight"] == [
        {"card_id": "card1", "stage": "ocr"},
        {"card_id": "card2", "stage": "date_verify"},
    ]
    assert d["done"] == ["card0"]
    assert d["errors"] == [{"card_id": "card3", "reason": "failed"}]
    assert d["queue"] == ["card4"]
    assert "current" not in d


def test_worker_starts_idle():
    """New worker starts in idle status with empty in_flight."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.in_flight == []
    assert status.done == []
    assert status.errors == []
    assert status.queue == []


@patch("src.web.worker.interpret_text")
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.extract_text")
def test_worker_processes_card(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Worker processes a card through OCR and LLM stages."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    worker = ExtractionWorker()
    started = worker.start(
        [(front, back)], text_dir, json_dir, tmp_path,
        "system", "template", MagicMock(),
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done
    assert mock_ocr.call_count == 2  # front + back
    assert mock_verify.call_count == 2  # front + back
    assert mock_interpret.call_count == 1


@patch("src.web.worker.extract_text", side_effect=RuntimeError("tesseract crashed"))
def test_worker_reports_ocr_errors(mock_ocr, tmp_path):
    """Cards with OCR failures go to errors, not the LLM queue."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], text_dir, tmp_path, tmp_path,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "Card"
    assert status.done == []


@patch("src.web.worker.extract_text")
def test_worker_skips_llm_without_backend(mock_ocr, tmp_path):
    """Without a backend, only OCR runs and cards go to done."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], text_dir, tmp_path, tmp_path,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done
    assert mock_ocr.call_count == 2


def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    def slow_ocr(*args, **kwargs):
        time.sleep(1)

    with patch("src.web.worker.extract_text", side_effect=slow_ocr):
        worker = ExtractionWorker()
        worker.start(
            [(front, back)], text_dir, tmp_path, tmp_path,
            None, None, None,
        )
        second = worker.start(
            [(front, back)], text_dir, tmp_path, tmp_path,
            None, None, None,
        )

    assert second is False


@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.interpret_text")
def test_worker_cancellation(mock_interpret, mock_verify, tmp_path):
    """Cancelling stops processing after the current card."""
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = tmp_path / f"{name}.jpeg"
        back = tmp_path / f"{name} 1.jpeg"
        front.touch()
        back.touch()
        pairs.append((front, back))

    def slow_ocr(*args, **kwargs):
        time.sleep(0.5)

    with patch("src.web.worker.extract_text", side_effect=slow_ocr):
        worker = ExtractionWorker()
        worker.start(
            pairs, text_dir, tmp_path, tmp_path,
            "sys", "tmpl", MagicMock(),
        )
        time.sleep(0.3)
        worker.cancel()

        for _ in range(50):
            time.sleep(0.1)
            status = worker.get_status()
            if status.status in ("idle", "cancelled"):
                break

    assert status.status in ("idle", "cancelled")
    total_processed = len(status.done) + len(status.errors)
    assert total_processed < 3


@patch("src.web.worker.interpret_text")
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.extract_text")
def test_worker_processes_multiple_cards(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """All cards in a batch are processed."""
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = tmp_path / f"{name}.jpeg"
        back = tmp_path / f"{name} 1.jpeg"
        front.touch()
        back.touch()
        pairs.append((front, back))

    worker = ExtractionWorker()
    worker.start(
        pairs, text_dir, json_dir, tmp_path,
        "sys", "tmpl", MagicMock(),
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert sorted(status.done) == ["Card A", "Card B", "Card C"]
    assert mock_ocr.call_count == 6
    assert mock_interpret.call_count == 3
