import json
import time
from pathlib import Path
from threading import Thread
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import pytest
from PIL import Image


def _start_test_server(json_dir, input_dir, output_dir, port=0):
    """Start an AppServer on a random port and return (server, base_url)."""
    from src.web.server import make_server

    server = make_server(json_dir, input_dir, output_dir, port=port)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://localhost:{actual_port}"


def test_get_root_returns_html(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/")
        body = resp.read().decode()
        assert "<!DOCTYPE html>" in body
    finally:
        server.shutdown()


def test_api_cards_returns_list(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (json_dir / "Card A.json").write_text('{"person": {}, "notes": [], "source": {}}')
    (json_dir / "Card B.json").write_text('{"person": {}, "notes": [], "source": {}}')

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/cards")
        data = json.loads(resp.read())
        assert data == ["Card A", "Card B"]
    finally:
        server.shutdown()


def test_api_card_detail_returns_data(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    card = {"person": {"first_name": "Jan"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt", "front_image_file": "Jan.jpeg", "back_image_file": "Jan 1.jpeg"}}
    (json_dir / "Jan.json").write_text(json.dumps(card))

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/cards/Jan")
        data = json.loads(resp.read())
        assert data["data"]["person"]["first_name"] == "Jan"
        assert data["front_image"] == "Jan.jpeg"
        assert data["back_image"] == "Jan 1.jpeg"
    finally:
        server.shutdown()


def test_api_card_not_found_returns_404(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/api/cards/nonexistent")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()


def test_api_put_card_saves_data(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    original = {"person": {"first_name": "old"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    (json_dir / "card.json").write_text(json.dumps(original))

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        updated = {"person": {"first_name": "new"}, "notes": ["fixed"], "source": {}}
        req = Request(
            f"{base}/api/cards/card",
            data=json.dumps(updated).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        resp = urlopen(req)
        assert resp.status == 200

        saved = json.loads((json_dir / "card.json").read_text())
        assert saved["person"]["first_name"] == "New"
        assert saved["source"]["front_text_file"] == "f.txt"
    finally:
        server.shutdown()


def test_images_endpoint_serves_jpeg(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (input_dir / "photo.jpeg").write_bytes(b"\xff\xd8fake jpeg content")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/images/photo.jpeg")
        assert resp.read() == b"\xff\xd8fake jpeg content"
        assert "image/jpeg" in resp.headers.get("Content-Type", "")
    finally:
        server.shutdown()


def test_images_path_traversal_returns_403(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/images/..%2Fsecret.jpeg")
        assert exc_info.value.code == 403
    finally:
        server.shutdown()


def test_output_images_serves_merged_jpeg(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "merged.jpeg").write_bytes(b"\xff\xd8merged content")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/output-images/merged.jpeg")
        assert resp.read() == b"\xff\xd8merged content"
        assert "image/jpeg" in resp.headers.get("Content-Type", "")
    finally:
        server.shutdown()


def test_output_images_path_traversal_returns_403(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/output-images/..%2Fsecret.jpeg")
        assert exc_info.value.code == 403
    finally:
        server.shutdown()


def _create_test_image(path, width=100, height=100, color="red"):
    """Create a small JPEG image for testing."""
    img = Image.new("RGB", (width, height), color)
    img.save(path, "JPEG")


def test_api_match_scan_returns_pairs(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/match/scan")
        data = json.loads(resp.read())
        assert len(data["pairs"]) == 1
        assert data["pairs"][0]["image_a"]["filename"] == "Card A.jpeg"
        assert data["pairs"][0]["image_b"]["filename"] == "Card A 1.jpeg"
        assert data["pairs"][0]["status"] == "auto_confirmed"
        assert "card_id" in data["pairs"][0]
    finally:
        server.shutdown()


def test_api_match_state_returns_snapshot(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        urlopen(f"{base}/api/match/scan")
        resp = urlopen(f"{base}/api/match/state")
        data = json.loads(resp.read())
        assert "pairs" in data
        assert "unmatched" in data
        assert "confirmed_count" in data
        assert data["confirmed_count"] == 1
    finally:
        server.shutdown()


def test_api_match_confirm_all_confirms_suggested_pairs(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        # Scan first, then confirm all
        urlopen(f"{base}/api/match/scan")
        req = Request(f"{base}/api/match/confirm-all", data=b"{}", method="POST",
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        data = json.loads(resp.read())
        assert data["status"] == "confirmed"
    finally:
        server.shutdown()





def test_api_match_unmatch_returns_to_unmatched(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        urlopen(f"{base}/api/match/scan")
        body = json.dumps({"image_a": "Card A.jpeg", "image_b": "Card A 1.jpeg"}).encode()
        req = Request(f"{base}/api/match/unmatch", data=body, method="POST",
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        data = json.loads(resp.read())
        assert data["status"] == "unmatched"

        state_resp = urlopen(f"{base}/api/match/state")
        state = json.loads(state_resp.read())
        assert len(state["unmatched"]) == 2
        assert len(state["pairs"]) == 0
    finally:
        server.shutdown()


def test_api_extract_status_idle_by_default(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/extract/status")
        data = json.loads(resp.read())
        assert data["status"] == "idle"
    finally:
        server.shutdown()


def test_api_extract_starts_and_completes(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create prompt files so the server loads them
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "extract_person_system.txt").write_text("system prompt")
    (prompts_dir / "vision_read.txt").write_text("vision prompt")

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        # Mock the backend so no real models are needed
        mock_backend = MagicMock()
        mock_backend.generate_vision.return_value = "Transcribed text"
        server.backend = mock_backend

        # Scan to populate match state (auto-confirms the pair)
        urlopen(f"{base}/api/match/scan")

        with patch("src.web.worker.interpret_transcription"):
            req = Request(f"{base}/api/extract", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
            resp = urlopen(req)
            data = json.loads(resp.read())
            assert data["status"] == "started"

            for _ in range(50):
                time.sleep(0.1)
                resp = urlopen(f"{base}/api/extract/status")
                status = json.loads(resp.read())
                if status["status"] == "idle":
                    break

            assert status["status"] == "idle"
            assert len(status["done"]) == 1
            assert "in_flight" in status
    finally:
        server.shutdown()


def test_api_extract_cancel_stops_worker(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create prompt files so the server loads them
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "extract_person_system.txt").write_text("system prompt")
    (prompts_dir / "vision_read.txt").write_text("vision prompt")

    # Create multiple pairs so there's something to cancel
    for name in ["Card A", "Card B", "Card C"]:
        _create_test_image(input_dir / f"{name}.jpeg", color="red")
        _create_test_image(input_dir / f"{name} 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        def slow_vision(*args, **kwargs):
            time.sleep(0.5)
            return "text"

        mock_backend = MagicMock()
        mock_backend.generate_vision.side_effect = slow_vision
        server.backend = mock_backend

        # Scan to populate match state
        urlopen(f"{base}/api/match/scan")

        with patch("src.web.worker.interpret_transcription"):
            req = Request(f"{base}/api/extract", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
            urlopen(req)

            time.sleep(0.3)

            cancel_req = Request(f"{base}/api/extract/cancel", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
            resp = urlopen(cancel_req)
            cancel_data = json.loads(resp.read())
            assert cancel_data["status"] == "cancelling"

            for _ in range(50):
                time.sleep(0.1)
                resp = urlopen(f"{base}/api/extract/status")
                status = json.loads(resp.read())
                if status["status"] in ("cancelled", "idle"):
                    break

            assert status["status"] in ("cancelled", "idle")
    finally:
        server.shutdown()


def test_api_extract_skips_already_extracted(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        scan_resp = urlopen(f"{base}/api/match/scan")
        scan_data = json.loads(scan_resp.read())
        card_id = scan_data["pairs"][0]["card_id"]

        # Enrich skeleton to simulate completed extraction
        json_path = json_dir / f"{card_id}.json"
        data = json.loads(json_path.read_text())
        data["person"] = {"first_name": "Card", "last_name": "A"}
        data["notes"] = []
        json_path.write_text(json.dumps(data))

        resp = urlopen(f"{base}/api/extract/cards")
        cards = json.loads(resp.read())
        assert len(cards["cards"]) == 1
        assert cards["cards"][0]["status"] == "done"
    finally:
        server.shutdown()


def test_api_extract_cards_lists_eligible(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Merged card, not yet extracted
    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")
    _create_test_image(output_dir / "Card A.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        # Scan to populate match state (auto-confirms the pair)
        urlopen(f"{base}/api/match/scan")
        resp = urlopen(f"{base}/api/extract/cards")
        data = json.loads(resp.read())
        assert len(data["cards"]) == 1
        assert "card_id" in data["cards"][0]
        assert data["cards"][0]["status"] == "pending"
    finally:
        server.shutdown()


def test_api_export_count_returns_json_count(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    (json_dir / "card1.json").write_text('{"person": {"first_name": "A"}, "notes": [], "source": {}}')
    (json_dir / "card2.json").write_text('{"person": {"first_name": "B"}, "notes": [], "source": {}}')
    (json_dir / "skeleton.json").write_text('{"source": {"front_image_file": "x.jpeg"}}')

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/export/count")
        data = json.loads(resp.read())
        assert data["count"] == 2
    finally:
        server.shutdown()


def test_html_contains_navigation_tabs(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/")
        body = resp.read().decode()
        assert "Match" in body
        assert "Extract" in body
        assert "Review" in body
        assert "#match" in body
        assert "#extract" in body
        assert "#review" in body
    finally:
        server.shutdown()
