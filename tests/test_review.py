import json
import pytest
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from src.review import list_cards, load_card, save_card


def test_list_cards_returns_sorted_stems(tmp_path):
    (tmp_path / "B card.json").write_text("{}")
    (tmp_path / "A card.json").write_text("{}")
    (tmp_path / "not_json.txt").write_text("")

    result = list_cards(tmp_path)

    assert result == ["A card", "B card"]


def test_list_cards_empty_dir(tmp_path):
    result = list_cards(tmp_path)

    assert result == []


def test_load_card_returns_json_and_image_paths(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    card_data = {
        "person": {"first_name": "Jan", "last_name": "Pansen"},
        "notes": [],
        "source": {
            "front_text_file": "Jan Pansen_front.txt",
            "back_text_file": "Jan Pansen 1_back.txt",
        },
    }
    (json_dir / "Jan Pansen.json").write_text(json.dumps(card_data))
    (input_dir / "Jan Pansen.jpeg").write_text("")
    (input_dir / "Jan Pansen 1.jpeg").write_text("")

    result = load_card("Jan Pansen", json_dir, input_dir)

    assert result["data"] == card_data
    assert result["front_image"] == "Jan Pansen.jpeg"
    assert result["back_image"] == "Jan Pansen 1.jpeg"


def test_load_card_missing_json_returns_none(tmp_path):
    result = load_card("nonexistent", tmp_path, tmp_path)

    assert result is None


def test_save_card_overwrites_json(tmp_path):
    original = {"person": {"first_name": "old"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {"person": {"first_name": "new"}, "notes": ["corrected"], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] == "new"


def test_save_card_preserves_source_from_disk(tmp_path):
    original = {"person": {"first_name": "old"}, "notes": [], "source": {"front_text_file": "real_front.txt", "back_text_file": "real_back.txt"}}
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {"person": {"first_name": "new"}, "notes": [], "source": {"front_text_file": "ignored.txt", "back_text_file": "ignored.txt"}}
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["source"]["front_text_file"] == "real_front.txt"
    assert result["source"]["back_text_file"] == "real_back.txt"


def _start_test_server(json_dir, input_dir, port=0):
    """Start a ReviewServer on a random port and return (server, base_url)."""
    from src.review import make_server

    server = make_server(json_dir, input_dir, port=port)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://localhost:{actual_port}"


def test_api_cards_returns_list(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (json_dir / "Card A.json").write_text('{"person": {}, "notes": [], "source": {}}')
    (json_dir / "Card B.json").write_text('{"person": {}, "notes": [], "source": {}}')

    server, base = _start_test_server(json_dir, input_dir)
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

    card = {"person": {"first_name": "Jan"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    (json_dir / "Jan.json").write_text(json.dumps(card))
    (input_dir / "Jan.jpeg").write_text("")
    (input_dir / "Jan 1.jpeg").write_text("")

    server, base = _start_test_server(json_dir, input_dir)
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

    server, base = _start_test_server(json_dir, input_dir)
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

    original = {"person": {"first_name": "old"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    (json_dir / "card.json").write_text(json.dumps(original))

    server, base = _start_test_server(json_dir, input_dir)
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
        assert saved["person"]["first_name"] == "new"
        assert saved["source"]["front_text_file"] == "f.txt"
    finally:
        server.shutdown()


def test_images_endpoint_serves_jpeg(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "photo.jpeg").write_bytes(b"\xff\xd8fake jpeg content")

    server, base = _start_test_server(json_dir, input_dir)
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

    server, base = _start_test_server(json_dir, input_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/images/..%2Fsecret.jpeg")
        assert exc_info.value.code == 403
    finally:
        server.shutdown()
