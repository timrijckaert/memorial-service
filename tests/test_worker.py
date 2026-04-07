# tests/test_worker.py
"""Tests for the ExtractionWorker background thread."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.extraction.pipeline import ExtractionResult
from src.web.worker import ExtractionWorker, ExtractionStatus, CardError


def test_worker_starts_idle():
    """New worker starts in idle status."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.current is None
    assert status.done == []
    assert status.errors == []
    assert status.queue == []


@patch("src.web.worker.extract_one")
def test_worker_processes_card(mock_extract, tmp_path):
    """Worker processes a card and moves it to done."""
    mock_extract.return_value = ExtractionResult(
        front_name="Card.jpeg", ocr_done=True, interpreted=True,
    )
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    worker = ExtractionWorker()
    started = worker.start(
        [(front, back)], tmp_path, tmp_path, tmp_path,
        None, None, None,
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done


@patch("src.web.worker.extract_one")
def test_worker_reports_errors(mock_extract, tmp_path):
    """Worker moves cards with errors to the errors list."""
    mock_extract.return_value = ExtractionResult(
        front_name="Card.jpeg", errors=["OCR failed"],
    )
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], tmp_path, tmp_path, tmp_path,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "Card"


def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    worker = ExtractionWorker()

    def slow_extract(*args, **kwargs):
        time.sleep(1)
        return ExtractionResult(front_name="test.jpeg")

    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    with patch("src.web.worker.extract_one", side_effect=slow_extract):
        worker.start(
            [(front, back)], tmp_path, tmp_path, tmp_path,
            None, None, None,
        )
        second = worker.start(
            [(front, back)], tmp_path, tmp_path, tmp_path,
            None, None, None,
        )

    assert second is False


def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict."""
    status = ExtractionStatus(
        status="running",
        current={"card_id": "test", "step": "ocr_front"},
        done=["card1"],
        errors=[CardError("card2", "failed")],
        queue=["card3"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["current"] == {"card_id": "test", "step": "ocr_front"}
    assert d["done"] == ["card1"]
    assert d["errors"] == [{"card_id": "card2", "reason": "failed"}]
    assert d["queue"] == ["card3"]
