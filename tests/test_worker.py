# tests/test_worker.py
"""Tests for the ExtractionWorker sequential pipeline."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from src.web.worker import ExtractionWorker, ExtractionStatus, CardError, CardProgress


def _make_test_image(path: Path) -> Path:
    """Create a minimal test image."""
    img = Image.new("RGB", (100, 50), "white")
    img.save(path, "JPEG")
    return path


def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict."""
    status = ExtractionStatus(
        status="running",
        in_flight=[CardProgress("card1", "vision_read")],
        done=["card0"],
        errors=[CardError("card3", "failed")],
        queue=["card4"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["in_flight"] == [{"card_id": "card1", "stage": "vision_read"}]
    assert d["done"] == ["card0"]
    assert d["errors"] == [{"card_id": "card3", "reason": "failed"}]
    assert d["queue"] == ["card4"]


def test_worker_starts_idle():
    """New worker starts in idle status."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.in_flight == []
    assert status.done == []
    assert status.errors == []
    assert status.queue == []


@patch("src.web.worker.interpret_transcription")
def test_worker_processes_card(mock_interpret, tmp_path):
    """Worker processes a card through vision read and text extract."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    backend = MagicMock()
    backend.generate_vision.return_value = "Dominicus Meganck"

    worker = ExtractionWorker()
    started = worker.start(
        [("test-uuid-001", front, back)], json_dir,
        "system prompt", "vision prompt", backend,
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "test-uuid-001" in status.done
    assert backend.generate_vision.call_count == 2  # one per side
    assert mock_interpret.call_count == 1


def test_worker_reports_vision_errors(tmp_path):
    """Cards with vision read failures go to errors."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    backend = MagicMock()
    backend.generate_vision.side_effect = RuntimeError("model crashed")

    worker = ExtractionWorker()
    worker.start(
        [("err-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "err-uuid"
    assert status.done == []


def test_worker_skips_without_backend(tmp_path):
    """Without a backend, cards go straight to done."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [("no-llm-uuid", front, back)], json_dir,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "no-llm-uuid" in status.done


def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    def slow_vision(*args, **kwargs):
        time.sleep(1)
        return "text"

    backend = MagicMock()
    backend.generate_vision.side_effect = slow_vision

    worker = ExtractionWorker()
    worker.start(
        [("dbl-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )
    second = worker.start(
        [("dbl-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )

    assert second is False


@patch("src.web.worker.interpret_transcription")
def test_worker_cancellation(mock_interpret, tmp_path):
    """Cancelling stops processing after the current card."""
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = _make_test_image(tmp_path / f"{name}.jpeg")
        back = _make_test_image(tmp_path / f"{name} 1.jpeg")
        pairs.append((f"cancel-{name}", front, back))

    def slow_vision(*args, **kwargs):
        time.sleep(0.5)
        return "text"

    backend = MagicMock()
    backend.generate_vision.side_effect = slow_vision

    worker = ExtractionWorker()
    worker.start(pairs, json_dir, "sys", "vis", backend)
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


@patch("src.web.worker.interpret_transcription")
def test_worker_processes_multiple_cards(mock_interpret, tmp_path):
    """All cards in a batch are processed."""
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = _make_test_image(tmp_path / f"{name}.jpeg")
        back = _make_test_image(tmp_path / f"{name} 1.jpeg")
        pairs.append((f"multi-{name}", front, back))

    backend = MagicMock()
    backend.generate_vision.return_value = "Some text"

    worker = ExtractionWorker()
    worker.start(pairs, json_dir, "sys", "vis", backend)

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert sorted(status.done) == sorted(["multi-Card A", "multi-Card B", "multi-Card C"])
    assert backend.generate_vision.call_count == 6  # 2 per card (front + back)
    assert mock_interpret.call_count == 3
