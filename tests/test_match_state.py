# tests/test_match_state.py
import json
import uuid
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


def test_confirm_creates_uuid_and_skeleton(tmp_path):
    """Confirming a pair assigns a UUID and writes a skeleton JSON to json_dir."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Unmatch an auto-confirmed pair, re-pair manually, then confirm
    state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    state.manual_pair("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    result = state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "confirmed"
    card_id = result["card_id"]
    # card_id should be a valid UUID
    uuid.UUID(card_id)

    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()
    data = json.loads(skeleton_path.read_text())
    assert data["source"]["front_image_file"] in ("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    assert data["source"]["back_image_file"] in ("Person A 1920.jpeg", "Person A 1920 1.jpeg")


def test_confirm_all_creates_uuids(tmp_path):
    """confirm_all assigns UUIDs to all newly confirmed pairs."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Unmatch both pairs so they become suggested when re-paired
    state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    state.unmatch("Person B 1950.jpeg", "Person B 1950 1.jpeg")
    state.manual_pair("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    state.manual_pair("Person B 1950.jpeg", "Person B 1950 1.jpeg")

    result = state.confirm_all()
    assert result["status"] == "confirmed"

    # All pairs should now have card_ids with skeleton files
    snapshot = state.get_snapshot()
    for pair in snapshot["pairs"]:
        if pair["status"] == "confirmed":
            assert "card_id" in pair
            card_id = pair["card_id"]
            uuid.UUID(card_id)
            skeleton_path = json_dir / f"{card_id}.json"
            assert skeleton_path.exists()


def test_mark_single_creates_uuid_and_skeleton(tmp_path):
    """Marking as single assigns UUID and writes skeleton with back_image_file=None."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    result = state.mark_single("orphan.jpeg")

    assert result["status"] == "single"
    card_id = result["card_id"]
    uuid.UUID(card_id)

    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()
    data = json.loads(skeleton_path.read_text())
    assert data["source"]["front_image_file"] == "orphan.jpeg"
    assert data["source"]["back_image_file"] is None


def test_scan_auto_confirmed_creates_uuids(tmp_path):
    """Auto-confirmed pairs during scan get UUIDs and skeleton files on disk."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)

    state.scan()

    snapshot = state.get_snapshot()
    for pair in snapshot["pairs"]:
        if pair["status"] == "auto_confirmed":
            assert "card_id" in pair
            card_id = pair["card_id"]
            uuid.UUID(card_id)
            skeleton_path = json_dir / f"{card_id}.json"
            assert skeleton_path.exists()


def test_unmatch_deletes_skeleton_json(tmp_path):
    """Unmatching a confirmed pair deletes its skeleton JSON from disk."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Get a pair that was auto-confirmed (has a card_id from scan)
    snapshot = state.get_snapshot()
    auto_pair = None
    for pair in snapshot["pairs"]:
        if pair["status"] == "auto_confirmed" and "card_id" in pair:
            auto_pair = pair
            break

    assert auto_pair is not None, "Expected at least one auto_confirmed pair"
    card_id = auto_pair["card_id"]
    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()

    # Unmatch the pair
    result = state.unmatch(
        auto_pair["image_a"]["filename"],
        auto_pair["image_b"]["filename"],
    )
    assert result["status"] == "unmatched"
    assert not skeleton_path.exists()


def test_confirm_auto_confirmed_keeps_existing_uuid(tmp_path):
    """Confirming an already auto-confirmed pair does NOT mint a new UUID."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = tmp_path / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    snapshot = state.get_snapshot()
    auto_pair = None
    for pair in snapshot["pairs"]:
        if pair["status"] == "auto_confirmed" and "card_id" in pair:
            auto_pair = pair
            break

    assert auto_pair is not None, "Expected at least one auto_confirmed pair"
    original_card_id = auto_pair["card_id"]

    # Confirm the auto-confirmed pair
    result = state.confirm(
        auto_pair["image_a"]["filename"],
        auto_pair["image_b"]["filename"],
    )

    assert result["status"] == "confirmed"
    assert result["card_id"] == original_card_id

    # Only one skeleton file should exist for this card
    skeleton_path = json_dir / f"{original_card_id}.json"
    assert skeleton_path.exists()
