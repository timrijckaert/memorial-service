# tests/test_match_state.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from PIL import Image

from src.web.match_state import MatchState


def _make_image(path, width=100, height=100):
    Image.new("RGB", (width, height)).save(path, "JPEG")


def _make_test_dir(tmp_path):
    """Create a test directory with 2 obvious pairs and 1 orphan."""
    _make_image(tmp_path / "Person A 1920.jpeg")
    _make_image(tmp_path / "Person A 1920 1.jpeg")
    _make_image(tmp_path / "Person B 1950.jpeg")
    _make_image(tmp_path / "Person B 1950 1.jpeg")
    _make_image(tmp_path / "orphan.jpeg")
    return tmp_path


def test_scan_populates_pairs_and_unmatched(tmp_path):
    _make_test_dir(tmp_path)
    state = MatchState(tmp_path, tmp_path / "output")

    result = state.scan()

    assert len(result["pairs"]) == 2
    assert len(result["unmatched"]) == 1


def test_confirm_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    result = state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "confirmed"


def test_unmatch_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()
    state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    result = state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "unmatched"
    snapshot = state.get_snapshot()
    # Both images should be in unmatched now
    unmatched_names = {u["filename"] for u in snapshot["unmatched"]}
    assert "Person A 1920.jpeg" in unmatched_names
    assert "Person A 1920 1.jpeg" in unmatched_names


def test_manual_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    # First unmatch a pair to get images into unmatched pool
    state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    result = state.manual_pair("Person A 1920.jpeg", "orphan.jpeg")

    assert result["status"] == "paired"
    snapshot = state.get_snapshot()
    paired_filenames = set()
    for p in snapshot["pairs"]:
        paired_filenames.add(p["image_a"]["filename"])
        paired_filenames.add(p["image_b"]["filename"])
    assert "Person A 1920.jpeg" in paired_filenames
    assert "orphan.jpeg" in paired_filenames


def test_mark_single(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    result = state.mark_single("orphan.jpeg")

    assert result["status"] == "single"
    snapshot = state.get_snapshot()
    assert "orphan.jpeg" in snapshot["singles"]
    unmatched_names = {u["filename"] for u in snapshot["unmatched"]}
    assert "orphan.jpeg" not in unmatched_names


def test_all_resolved_when_confirmed_and_singles(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    # Auto-confirmed pairs count as resolved
    state.mark_single("orphan.jpeg")

    snapshot = state.get_snapshot()
    assert snapshot["all_resolved"] is True


def test_not_all_resolved_with_unmatched(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    snapshot = state.get_snapshot()
    # orphan is still unmatched
    assert snapshot["all_resolved"] is False


def test_get_confirmed_pairs_for_extract(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()
    state.mark_single("orphan.jpeg")

    pairs, singles = state.get_confirmed_items()

    assert len(pairs) == 2
    assert len(singles) == 1
    assert singles[0].name == "orphan.jpeg"
