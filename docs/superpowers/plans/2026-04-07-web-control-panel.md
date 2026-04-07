# Web Control Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CLI-driven workflow with a web UI that serves as the single entry point for merge, extraction, and review.

**Architecture:** A new `server.py` module serves a single-page application and REST API. It imports and delegates to `merge.py`, `extract.py`, and the data-access layer extracted from `review.py`. Extraction runs on a background thread (sequential, one card at a time). The frontend polls status endpoints during active operations.

**Tech Stack:** Python `http.server`, `threading`, inline HTML/JS/CSS (no frameworks, no new dependencies)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/server.py` (create) | HTTP server, API routes, background extraction worker, inline SPA HTML/JS/CSS |
| `src/review.py` (modify) | Data-access only: `list_cards`, `load_card`, `save_card`, `_find_image`. Remove `ReviewHandler`, `REVIEW_HTML`, `make_server`, `start_review`. |
| `src/main.py` (modify) | Default command becomes `serve` (start web server). Keep `merge`/`extract` CLI subcommands. |
| `tests/test_server.py` (create) | Tests for all new API routes and worker behavior |
| `tests/test_review.py` (modify) | Remove HTTP server tests (moved to `test_server.py`). Keep data-access tests. |

---

### Task 1: Extract data-access layer from review.py

Strip `review.py` down to just the data-access functions. Remove all HTTP/HTML/server code.

**Files:**
- Modify: `src/review.py`
- Modify: `tests/test_review.py`

- [ ] **Step 1: Write a test that imports only data-access functions**

```python
# tests/test_review.py — add at the top, replacing the existing import
from src.review import list_cards, load_card, save_card
```

Verify the existing data-access tests (`test_list_cards_returns_sorted_stems`, `test_list_cards_empty_dir`, `test_load_card_returns_json_and_image_paths`, `test_load_card_missing_json_returns_none`, `test_save_card_overwrites_json`, `test_save_card_preserves_source_from_disk`) still pass after the refactor.

- [ ] **Step 2: Run existing data-access tests to confirm they pass before refactoring**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_review.py::test_list_cards_returns_sorted_stems tests/test_review.py::test_list_cards_empty_dir tests/test_review.py::test_load_card_returns_json_and_image_paths tests/test_review.py::test_load_card_missing_json_returns_none tests/test_review.py::test_save_card_overwrites_json tests/test_review.py::test_save_card_preserves_source_from_disk -v`
Expected: All 6 PASS

- [ ] **Step 3: Strip review.py to data-access only**

Replace the entire contents of `src/review.py` with just the data-access functions:

```python
import json
from pathlib import Path

JPEG_EXTENSIONS = (".jpeg", ".jpg")


def list_cards(json_dir: Path) -> list[str]:
    """Return sorted list of card ID stems from JSON files in the directory."""
    return sorted(p.stem for p in json_dir.iterdir() if p.suffix == ".json")


def _find_image(input_dir: Path, stem: str) -> str | None:
    """Find a JPEG file matching the given stem in input_dir."""
    for ext in JPEG_EXTENSIONS:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate.name
    return None


def load_card(card_id: str, json_dir: Path, input_dir: Path) -> dict | None:
    """Load card JSON and resolve front/back image filenames. Returns None if not found."""
    json_path = json_dir / f"{card_id}.json"
    if not json_path.exists():
        return None

    data = json.loads(json_path.read_text())
    front_image = _find_image(input_dir, card_id)
    back_image = _find_image(input_dir, f"{card_id} 1")

    return {
        "data": data,
        "front_image": front_image,
        "back_image": back_image,
    }


def save_card(card_id: str, json_dir: Path, updated_data: dict) -> None:
    """Save corrected card data, preserving the original source field from disk."""
    json_path = json_dir / f"{card_id}.json"
    original = json.loads(json_path.read_text())
    merged = {**updated_data, "source": original["source"]}
    json_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Strip test_review.py to data-access tests only**

Remove all HTTP server tests and the `_start_test_server` helper from `tests/test_review.py`. Keep only these tests:
- `test_list_cards_returns_sorted_stems`
- `test_list_cards_empty_dir`
- `test_load_card_returns_json_and_image_paths`
- `test_load_card_missing_json_returns_none`
- `test_save_card_overwrites_json`
- `test_save_card_preserves_source_from_disk`

Remove all imports that are no longer needed: `Thread`, `HTTPError`, `urlopen`, `Request`, `patch`, `pytest` (if no longer used — but `pytest` is still needed if any test uses `tmp_path`). The file should look like:

```python
import json
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
```

- [ ] **Step 5: Run data-access tests to verify refactor**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_review.py -v`
Expected: All 6 PASS

- [ ] **Step 6: Commit**

```bash
git add src/review.py tests/test_review.py
git commit -m "refactor: strip review.py to data-access layer only"
```

---

### Task 2: Create server.py with review API routes (ported from old review.py)

Port the HTTP server, image serving, and review API routes from the old `review.py` into the new `server.py`. This re-establishes the existing review functionality under the new server.

**Files:**
- Create: `src/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for review API routes**

Create `tests/test_server.py` with the review API tests (ported from the old `test_review.py`):

```python
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import pytest


def _start_test_server(json_dir, input_dir, output_dir, port=0):
    """Start an AppServer on a random port and return (server, base_url)."""
    from src.server import make_server

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

    card = {"person": {"first_name": "Jan"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    (json_dir / "Jan.json").write_text(json.dumps(card))
    (input_dir / "Jan.jpeg").write_text("")
    (input_dir / "Jan 1.jpeg").write_text("")

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
        assert saved["person"]["first_name"] == "new"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: FAIL (ImportError — `src.server` does not exist)

- [ ] **Step 3: Create server.py with review API routes and HTML serving**

Create `src/server.py`. For now, use a minimal placeholder HTML string (just enough to pass the `<!DOCTYPE html>` test). The full SPA HTML will be built in Task 6.

```python
import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from src.review import list_cards, load_card, save_card

# Placeholder HTML — replaced with full SPA in a later task
APP_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Memorial Card Digitizer</title></head>
<body><h1>Memorial Card Digitizer</h1><p>Under construction</p></body>
</html>
"""


class AppHandler(BaseHTTPRequestHandler):
    """HTTP handler for the memorial card web app."""

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _serve_image(self, base_dir: Path, filename: str):
        image_path = (base_dir / filename).resolve()
        if not str(image_path).startswith(str(base_dir.resolve())):
            self._send_error(403, "Forbidden")
            return
        if not image_path.exists():
            self._send_error(404, "Image not found")
            return

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = image_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        json_dir = self.server.json_dir
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir

        if self.path == "/":
            body = APP_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/cards":
            self._send_json(list_cards(json_dir))
        elif self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            result = load_card(card_id, json_dir, input_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                self._send_json(result)
        elif self.path.startswith("/images/"):
            filename = unquote(self.path[len("/images/"):])
            self._serve_image(input_dir, filename)
        elif self.path.startswith("/output-images/"):
            filename = unquote(self.path[len("/output-images/"):])
            self._serve_image(output_dir, filename)
        else:
            self._send_error(404, "Not found")

    def do_PUT(self):
        json_dir = self.server.json_dir

        if self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                updated_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return

            json_path = json_dir / f"{card_id}.json"
            if not json_path.exists():
                self._send_error(404, "Card not found")
                return

            save_card(card_id, json_dir, updated_data)
            self._send_json({"status": "saved"})
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        self._send_error(404, "Not found")


def make_server(json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    return server
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: All 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: create server.py with review API routes and image serving"
```

---

### Task 3: Add output-images endpoint and merge pairs API

Add the route to serve merged images from `output/` and the merge pairs listing endpoint.

**Files:**
- Modify: `tests/test_server.py`
- Modify: `src/server.py`

- [ ] **Step 1: Write failing tests for output-images and merge pairs**

Add to `tests/test_server.py`:

```python
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


def test_api_merge_pairs_returns_detected_pairs(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create a valid pair
    (input_dir / "De Smet Maria.jpeg").write_bytes(b"\xff\xd8front")
    (input_dir / "De Smet Maria 1.jpeg").write_bytes(b"\xff\xd8back")
    # Create an orphan (no back)
    (input_dir / "Orphan Jan.jpeg").write_bytes(b"\xff\xd8front")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/merge/pairs")
        data = json.loads(resp.read())
        assert len(data["pairs"]) == 1
        assert data["pairs"][0]["name"] == "De Smet Maria"
        assert data["pairs"][0]["front"] == "De Smet Maria.jpeg"
        assert data["pairs"][0]["back"] == "De Smet Maria 1.jpeg"
        assert len(data["errors"]) == 1
        assert "Orphan Jan" in data["errors"][0]
    finally:
        server.shutdown()


def test_api_merge_pairs_shows_already_merged(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    (input_dir / "Card A.jpeg").write_bytes(b"\xff\xd8front")
    (input_dir / "Card A 1.jpeg").write_bytes(b"\xff\xd8back")
    # Already merged
    (output_dir / "Card A.jpeg").write_bytes(b"\xff\xd8merged")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/merge/pairs")
        data = json.loads(resp.read())
        assert data["pairs"][0]["merged"] is True
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py::test_output_images_serves_merged_jpeg tests/test_server.py::test_output_images_path_traversal_returns_403 tests/test_server.py::test_api_merge_pairs_returns_detected_pairs tests/test_server.py::test_api_merge_pairs_shows_already_merged -v`
Expected: `test_output_images_*` already PASS (route exists from Task 2). `test_api_merge_pairs_*` FAIL (route not yet handled).

- [ ] **Step 3: Add merge pairs API route to server.py**

In `src/server.py`, add the import at the top:

```python
from src.merge import find_pairs
```

In `do_GET`, add this `elif` branch before the `else` at the end:

```python
        elif self.path == "/api/merge/pairs":
            pairs, errors = find_pairs(input_dir)
            result = {
                "pairs": [
                    {
                        "name": front.stem,
                        "front": front.name,
                        "back": back.name,
                        "merged": (output_dir / front.name).exists(),
                    }
                    for front, back in pairs
                ],
                "errors": errors,
            }
            self._send_json(result)
```

- [ ] **Step 4: Run all server tests**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add output-images endpoint and merge pairs API"
```

---

### Task 4: Add merge trigger API (POST /api/merge)

Add the endpoint that triggers merging all valid pairs synchronously.

**Files:**
- Modify: `tests/test_server.py`
- Modify: `src/server.py`

- [ ] **Step 1: Write failing tests for POST /api/merge**

Add to `tests/test_server.py`:

```python
from PIL import Image
import io


def _create_test_image(path, width=100, height=100, color="red"):
    """Create a small JPEG image for testing."""
    img = Image.new("RGB", (width, height), color)
    img.save(path, "JPEG")


def test_api_merge_triggers_stitching(tmp_path):
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
        req = Request(f"{base}/api/merge", data=b"{}", method="POST",
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        data = json.loads(resp.read())
        assert data["ok"] == 1
        assert data["errors"] == []
        assert (output_dir / "Card A.jpeg").exists()
    finally:
        server.shutdown()


def test_api_merge_skips_already_merged(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")
    # Pre-existing merged file
    _create_test_image(output_dir / "Card A.jpeg", color="green")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        req = Request(f"{base}/api/merge", data=b"{}", method="POST",
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        data = json.loads(resp.read())
        assert data["ok"] == 0
        assert data["skipped"] == 1
    finally:
        server.shutdown()


def test_api_merge_with_force_reprocesses(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")
    _create_test_image(output_dir / "Card A.jpeg", color="green")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        req = Request(f"{base}/api/merge", data=json.dumps({"force": True}).encode(),
                      method="POST", headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        data = json.loads(resp.read())
        assert data["ok"] == 1
        assert data["skipped"] == 0
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py::test_api_merge_triggers_stitching tests/test_server.py::test_api_merge_skips_already_merged tests/test_server.py::test_api_merge_with_force_reprocesses -v`
Expected: FAIL (POST returns 404)

- [ ] **Step 3: Implement POST /api/merge in server.py**

In `src/server.py`, add the import at the top:

```python
from src.merge import find_pairs, merge_all
```

(Replace the existing `from src.merge import find_pairs` line.)

Replace the `do_POST` method:

```python
    def do_POST(self):
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir

        if self.path == "/api/merge":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            pairs, pairing_errors = find_pairs(input_dir)
            ok_count, skipped, merge_errors = merge_all(pairs, output_dir, force=force)
            self._send_json({
                "ok": ok_count,
                "skipped": skipped,
                "errors": pairing_errors + merge_errors,
            })
        else:
            self._send_error(404, "Not found")
```

- [ ] **Step 4: Run all server tests**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add POST /api/merge endpoint for triggering merge"
```

---

### Task 5: Add extraction worker and API routes

Add the background extraction worker thread and the extract API routes: POST to start, GET status, POST cancel.

**Files:**
- Modify: `src/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for extraction API**

Add to `tests/test_server.py`:

```python
import time
from unittest.mock import patch


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
    text_dir = output_dir / "text"
    text_dir.mkdir()

    _create_test_image(input_dir / "Card A.jpeg", color="red")
    _create_test_image(input_dir / "Card A 1.jpeg", color="blue")
    # Pre-merge
    _create_test_image(output_dir / "Card A.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with patch("src.extract._extract_one") as mock_extract:
            mock_extract.return_value = {
                "front_name": "Card A.jpeg",
                "ocr": True,
                "verify_corrections": 0,
                "interpreted": True,
                "errors": [],
                "date_fixes": [],
            }

            req = Request(f"{base}/api/extract", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
            resp = urlopen(req)
            data = json.loads(resp.read())
            assert data["status"] == "started"

            # Wait for worker to finish
            for _ in range(50):
                time.sleep(0.1)
                resp = urlopen(f"{base}/api/extract/status")
                status = json.loads(resp.read())
                if status["status"] == "idle":
                    break

            assert status["status"] == "idle"
            assert len(status["done"]) == 1
    finally:
        server.shutdown()


def test_api_extract_cancel_stops_worker(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    text_dir = output_dir / "text"
    text_dir.mkdir()

    # Create multiple pairs so there's something to cancel
    for name in ["Card A", "Card B", "Card C"]:
        _create_test_image(input_dir / f"{name}.jpeg", color="red")
        _create_test_image(input_dir / f"{name} 1.jpeg", color="blue")
        _create_test_image(output_dir / f"{name}.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        def slow_extract(*args, **kwargs):
            time.sleep(0.5)
            return {
                "front_name": "test.jpeg",
                "ocr": True,
                "verify_corrections": 0,
                "interpreted": True,
                "errors": [],
                "date_fixes": [],
            }

        with patch("src.extract._extract_one", side_effect=slow_extract):
            # Start extraction
            req = Request(f"{base}/api/extract", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
            urlopen(req)

            # Give it a moment to start processing
            time.sleep(0.2)

            # Cancel
            cancel_req = Request(f"{base}/api/extract/cancel", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
            resp = urlopen(cancel_req)
            cancel_data = json.loads(resp.read())
            assert cancel_data["status"] == "cancelling"

            # Wait for it to finish current card and stop
            for _ in range(50):
                time.sleep(0.1)
                resp = urlopen(f"{base}/api/extract/status")
                status = json.loads(resp.read())
                if status["status"] == "cancelled":
                    break

            assert status["status"] == "cancelled"
            # Should not have processed all 3
            assert len(status["done"]) + len(status["queue"]) < 3 or len(status["queue"]) > 0
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
    _create_test_image(output_dir / "Card A.jpeg", color="red")
    # Already extracted
    (json_dir / "Card A.json").write_text('{"person": {}, "notes": [], "source": {}}')

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/extract/cards")
        data = json.loads(resp.read())
        assert len(data["cards"]) == 1
        assert data["cards"][0]["status"] == "done"
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
        resp = urlopen(f"{base}/api/extract/cards")
        data = json.loads(resp.read())
        assert len(data["cards"]) == 1
        assert data["cards"][0]["name"] == "Card A"
        assert data["cards"][0]["status"] == "pending"
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py::test_api_extract_status_idle_by_default tests/test_server.py::test_api_extract_cards_lists_eligible -v`
Expected: FAIL (routes not found)

- [ ] **Step 3: Add extraction worker and API routes to server.py**

In `src/server.py`, add these imports at the top:

```python
import threading
from src.extract import _extract_one
```

Add the `ExtractionWorker` class after the imports, before `AppHandler`:

```python
class ExtractionWorker:
    """Runs extraction sequentially on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = {
            "status": "idle",
            "current": None,
            "done": [],
            "errors": [],
            "queue": [],
        }

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              prompt_template, ollama_available, force):
        with self._lock:
            if self._state["status"] == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._state = {
                "status": "running",
                "current": None,
                "done": [],
                "errors": [],
                "queue": queue_names,
            }
            self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  prompt_template, ollama_available, force),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        self._cancel.set()
        with self._lock:
            if self._state["status"] == "running":
                self._state["status"] = "cancelling"

    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             prompt_template, ollama_available, force):
        for front_path, back_path in pairs:
            if self._cancel.is_set():
                with self._lock:
                    self._state["status"] = "cancelled"
                return

            card_name = front_path.stem

            with self._lock:
                if card_name in self._state["queue"]:
                    self._state["queue"].remove(card_name)
                self._state["current"] = {"card_id": card_name, "step": "ocr_front"}

            # Skip if already extracted and not forcing
            json_output = json_dir / f"{front_path.stem}.json"
            if not force and json_output.exists():
                with self._lock:
                    self._state["done"].append(card_name)
                    self._state["current"] = None
                continue

            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, prompt_template,
            )

            with self._lock:
                if result["errors"]:
                    self._state["errors"].append({
                        "card_id": card_name,
                        "reason": "; ".join(result["errors"]),
                    })
                else:
                    self._state["done"].append(card_name)
                self._state["current"] = None

        with self._lock:
            if self._state["status"] != "cancelled":
                self._state["status"] = "idle"
```

In the `do_GET` method, add these branches before the `else`:

```python
        elif self.path == "/api/extract/status":
            self._send_json(self.server.worker.get_status())
        elif self.path == "/api/extract/cards":
            pairs, _ = find_pairs(input_dir)
            cards = []
            for front, back in pairs:
                has_json = (json_dir / f"{front.stem}.json").exists()
                cards.append({
                    "name": front.stem,
                    "front": front.name,
                    "back": back.name,
                    "status": "done" if has_json else "pending",
                })
            self._send_json({"cards": cards})
```

In the `do_POST` method, add these branches. The full method becomes:

```python
    def do_POST(self):
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir
        json_dir = self.server.json_dir

        if self.path == "/api/merge":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            pairs, pairing_errors = find_pairs(input_dir)
            ok_count, skipped, merge_errors = merge_all(pairs, output_dir, force=force)
            self._send_json({
                "ok": ok_count,
                "skipped": skipped,
                "errors": pairing_errors + merge_errors,
            })
        elif self.path == "/api/extract":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            pairs, _ = find_pairs(input_dir)
            text_dir = output_dir / "text"
            text_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)
            conflicts_dir = output_dir / "date_conflicts"

            # Load prompt template
            prompt_path = input_dir.parent / "prompts" / "extract_person.txt"
            prompt_template = None
            if prompt_path.exists():
                prompt_template = prompt_path.read_text()

            # Check Ollama availability
            ollama_available = False
            if prompt_template:
                try:
                    import ollama as ollama_client
                    ollama_client.list()
                    ollama_available = True
                except Exception:
                    pass

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                prompt_template, ollama_available, force,
            )
            if started:
                self._send_json({"status": "started"})
            else:
                self._send_json({"status": "already_running"}, 409)
        elif self.path == "/api/extract/cancel":
            self.server.worker.cancel()
            self._send_json({"status": "cancelling"})
        else:
            self._send_error(404, "Not found")
```

In the `make_server` function, add the worker:

```python
def make_server(json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    server.worker = ExtractionWorker()
    return server
```

- [ ] **Step 4: Run all server tests**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add extraction worker and extract API routes"
```

---

### Task 6: Build the SPA HTML/JS/CSS

Replace the placeholder HTML in `server.py` with the full single-page application: navigation tabs, merge section, extract section, and review section.

**Files:**
- Modify: `src/server.py`

- [ ] **Step 1: Write a test for hash-based navigation**

Add to `tests/test_server.py`:

```python
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
        assert "Merge" in body
        assert "Extract" in body
        assert "Review" in body
        assert "#merge" in body
        assert "#extract" in body
        assert "#review" in body
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py::test_html_contains_navigation_tabs -v`
Expected: FAIL (placeholder HTML doesn't have these elements)

- [ ] **Step 3: Replace APP_HTML with full SPA**

Replace the `APP_HTML` string in `src/server.py` with the full single-page application. This is a large string — the complete HTML/CSS/JS for all three sections.

```python
APP_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memorial Card Digitizer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #333; }

  /* Navigation */
  .nav-bar { display: flex; background: #1a1a2e; border-bottom: 1px solid #333; }
  .nav-tab { padding: 12px 24px; color: #888; cursor: pointer; font-size: 14px; font-weight: 600; border-bottom: 2px solid transparent; text-decoration: none; }
  .nav-tab:hover { color: #ccc; }
  .nav-tab.active { color: #fff; border-bottom-color: #4a90d9; }

  /* Sections */
  .section { display: none; min-height: calc(100vh - 45px); }
  .section.active { display: block; }

  /* Merge section */
  .merge-section { padding: 24px; }
  .merge-controls { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
  .merge-hint { color: #888; font-size: 14px; margin-bottom: 16px; }
  .merge-hint code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; }
  .merge-summary { margin-bottom: 16px; font-size: 14px; }
  .merge-summary .ok { color: #27ae60; }
  .merge-summary .err { color: #e74c3c; }
  .merge-summary .skip { color: #888; }
  .pairs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .pair-card { background: #fff; border-radius: 8px; overflow: hidden; border: 1px solid #ddd; }
  .pair-card.error { border-color: #e74c3c; border-style: dashed; }
  .pair-card.merged { border-color: #27ae60; }
  .pair-images { display: flex; height: 150px; background: #f0f0f0; }
  .pair-images img { flex: 1; object-fit: cover; max-width: 50%; }
  .pair-images .merged-img { max-width: 100%; }
  .pair-images .placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; font-size: 12px; background: #e8e8e8; }
  .pair-images .placeholder.missing { background: #fde8e8; color: #e74c3c; }
  .pair-name { padding: 8px 12px; font-size: 13px; }
  .pair-name .status { font-size: 11px; margin-left: 4px; }

  /* Extract section */
  .extract-section { padding: 24px; }
  .extract-controls { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
  .extract-controls label { font-size: 13px; color: #666; display: flex; align-items: center; gap: 4px; }
  .extract-summary { display: flex; gap: 16px; margin-bottom: 16px; font-size: 13px; color: #888; }
  .current-card { background: #fff; border: 2px solid #4a90d9; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .current-card .card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .current-card .card-header .dot { width: 8px; height: 8px; border-radius: 50%; background: #4a90d9; animation: pulse 1s infinite; }
  .current-card .card-header .name { font-weight: 600; }
  .current-card .card-header .label { color: #4a90d9; font-size: 12px; margin-left: auto; }
  .pipeline-steps { display: flex; gap: 4px; margin-bottom: 12px; }
  .pipeline-step { flex: 1; padding: 6px; border-radius: 4px; font-size: 11px; text-align: center; background: #f0f0f0; color: #999; }
  .pipeline-step.done { background: #e8f5e9; color: #27ae60; }
  .pipeline-step.active { background: #e3f2fd; color: #4a90d9; border: 1px solid #4a90d9; }
  .ocr-preview { background: #f8f8f8; border-radius: 4px; padding: 8px; font-size: 12px; color: #666; font-family: monospace; max-height: 100px; overflow: auto; white-space: pre-wrap; }
  .card-list { display: flex; flex-direction: column; gap: 4px; }
  .card-item { display: flex; align-items: center; padding: 8px 12px; background: #fff; border-radius: 6px; border: 1px solid #ddd; gap: 12px; font-size: 13px; }
  .card-item.in-progress { border-color: #4a90d9; }
  .card-item.queued { opacity: 0.5; }
  .card-item .icon { font-size: 14px; width: 20px; text-align: center; }
  .card-item .icon.done { color: #27ae60; }
  .card-item .icon.error { color: #e74c3c; }
  .card-item .icon.progress { color: #4a90d9; }
  .card-item .icon.queued { color: #999; }
  .card-item .name { flex: 1; }
  .card-item .status-text { font-size: 11px; color: #888; }
  .card-item .review-link { color: #4a90d9; font-size: 11px; text-decoration: underline; cursor: pointer; }
  .extract-error-msg { background: #fde8e8; border: 1px solid #e74c3c; border-radius: 6px; padding: 12px; color: #c0392b; font-size: 14px; margin-bottom: 16px; }

  /* Review section */
  .review-section { display: none; height: calc(100vh - 45px); }
  .review-section.active { display: flex; }
  .review-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 24px; background: #fff; border-bottom: 1px solid #ddd; }
  .review-nav { display: flex; gap: 8px; align-items: center; }
  .review-nav button { padding: 6px 16px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; }
  .review-nav button:hover { background: #eee; }
  .review-nav button:disabled { opacity: 0.4; cursor: default; }
  .review-counter { font-size: 14px; color: #666; min-width: 80px; text-align: center; }
  .review-main { display: flex; flex: 1; overflow: hidden; }
  .image-panel { flex: 1; display: flex; flex-direction: column; border-right: 1px solid #ddd; background: #222; }
  .image-toggle { display: flex; background: #333; }
  .image-toggle button { flex: 1; padding: 8px; border: none; background: #333; color: #aaa; cursor: pointer; font-size: 13px; }
  .image-toggle button.active { background: #555; color: #fff; }
  .image-container { flex: 1; display: flex; align-items: center; justify-content: center; overflow: auto; padding: 16px; }
  .image-container img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .form-panel { flex: 1; overflow-y: auto; padding: 24px; background: #fff; }
  .form-group { margin-bottom: 16px; }
  .form-group label { display: block; font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; margin-bottom: 4px; }
  .form-group input { width: 100%; padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .form-group input:focus { outline: none; border-color: #4a90d9; }
  .section-title { font-size: 14px; font-weight: 600; color: #333; margin: 20px 0 12px; padding-bottom: 4px; border-bottom: 1px solid #eee; }
  .notes-list { list-style: none; padding: 0; }
  .notes-list li { font-size: 13px; color: #666; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
  .spouse-entry { display: flex; gap: 6px; margin-bottom: 6px; }
  .spouse-entry input { flex: 1; padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .spouse-entry input:focus { outline: none; border-color: #4a90d9; }
  .spouse-entry button { padding: 4px 10px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; color: #999; }
  .spouse-entry button:hover { background: #fee; color: #c00; border-color: #c00; }
  .no-image { color: #888; font-style: italic; }
  .no-cards-msg { padding: 40px; text-align: center; color: #888; font-size: 16px; }

  /* Shared */
  .btn { padding: 10px 24px; border: none; border-radius: 6px; font-weight: 600; font-size: 14px; cursor: pointer; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-primary { background: #4a90d9; color: #fff; }
  .btn-primary:hover:not(:disabled) { background: #3a7bc8; }
  .btn-danger { background: #e74c3c; color: #fff; }
  .btn-danger:hover:not(:disabled) { background: #c0392b; }
  .btn-success { background: #27ae60; color: #fff; }
  .btn-success:hover:not(:disabled) { background: #219a52; }
  .add-spouse-btn { padding: 6px 12px; border: 1px dashed #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; color: #666; }
  .add-spouse-btn:hover { border-color: #4a90d9; color: #4a90d9; }

  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
</head>
<body>

<!-- Navigation -->
<nav class="nav-bar">
  <a class="nav-tab" href="#merge" onclick="showSection('merge')">Merge</a>
  <a class="nav-tab" href="#extract" onclick="showSection('extract')">Extract</a>
  <a class="nav-tab" href="#review" onclick="showSection('review')">Review</a>
</nav>

<!-- Merge Section -->
<div id="section-merge" class="section merge-section">
  <div class="merge-controls">
    <button id="merge-btn" class="btn btn-primary" onclick="triggerMerge()">Merge All</button>
    <span id="merge-pair-count" style="color:#888; font-size:14px;"></span>
  </div>
  <p class="merge-hint">Drop your scanned front &amp; back images in the <code>input/</code> folder and refresh the page.</p>
  <div id="merge-summary" class="merge-summary" style="display:none;"></div>
  <div id="pairs-grid" class="pairs-grid"></div>
</div>

<!-- Extract Section -->
<div id="section-extract" class="section extract-section">
  <div class="extract-controls">
    <button id="extract-btn" class="btn btn-primary" onclick="triggerExtract()">Extract All</button>
    <button id="cancel-btn" class="btn btn-danger" onclick="cancelExtract()" style="display:none;">Cancel</button>
    <label><input type="checkbox" id="force-extract"> Force re-extract</label>
    <span id="extract-count" style="color:#888; font-size:14px;"></span>
  </div>
  <div id="extract-error" class="extract-error-msg" style="display:none;"></div>
  <div id="extract-summary" class="extract-summary" style="display:none;"></div>
  <div id="current-card" class="current-card" style="display:none;">
    <div class="card-header">
      <div class="dot"></div>
      <span class="name" id="current-name"></span>
      <span class="label">Currently processing</span>
    </div>
    <div class="pipeline-steps" id="pipeline-steps">
      <div class="pipeline-step" data-step="ocr_front">OCR Front</div>
      <div class="pipeline-step" data-step="ocr_back">OCR Back</div>
      <div class="pipeline-step" data-step="date_verify">Date Verify</div>
      <div class="pipeline-step" data-step="llm_extract">LLM Extract</div>
    </div>
  </div>
  <div id="extract-card-list" class="card-list"></div>
</div>

<!-- Review Section -->
<div id="section-review" class="section review-section">
  <div style="display:flex; flex-direction:column; flex:1;">
    <div class="review-header">
      <div class="review-nav">
        <button id="prev-btn" onclick="reviewNavigate(-1)">&larr; Previous</button>
        <span id="review-counter" class="review-counter">-</span>
        <button id="next-btn" onclick="reviewNavigate(1)">Next &rarr;</button>
      </div>
    </div>
    <div class="review-main">
      <div class="image-panel">
        <div class="image-toggle">
          <button id="front-btn" onclick="showSide('front')">Front</button>
          <button id="back-btn" class="active" onclick="showSide('back')">Back</button>
        </div>
        <div class="image-container">
          <img id="card-image" src="" alt="Card image">
          <span id="no-image" class="no-image" style="display:none">No image available</span>
        </div>
      </div>
      <div class="form-panel">
        <div class="section-title">Person</div>
        <div class="form-group"><label>First Name</label><input id="f-first_name"></div>
        <div class="form-group"><label>Last Name</label><input id="f-last_name"></div>
        <div class="form-group"><label>Birth Date (YYYY-MM-DD)</label><input id="f-birth_date"></div>
        <div class="form-group"><label>Birth Place</label><input id="f-birth_place"></div>
        <div class="form-group"><label>Death Date (YYYY-MM-DD)</label><input id="f-death_date"></div>
        <div class="form-group"><label>Death Place</label><input id="f-death_place"></div>
        <div class="form-group"><label>Age at Death</label><input id="f-age_at_death" type="number"></div>
        <div class="form-group"><label>Spouses</label><div id="spouses-list"></div><button type="button" class="add-spouse-btn" onclick="addSpouseInput('')">+ Add spouse</button></div>
        <div class="section-title">Notes (from LLM)</div>
        <ul id="notes-list" class="notes-list"></ul>
        <button id="approve-btn" class="btn btn-primary" style="width:100%; margin-top:24px;" onclick="approveCard()">Approve</button>
      </div>
    </div>
    <div id="no-cards" class="no-cards-msg" style="display:none;">No cards to review. Run extraction first.</div>
  </div>
</div>

<script>
/* ---- Navigation ---- */
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));

  const section = document.getElementById('section-' + name);
  if (section) section.classList.add('active');

  const tab = document.querySelector('.nav-tab[href="#' + name + '"]');
  if (tab) tab.classList.add('active');

  if (name === 'merge') loadMergePairs();
  if (name === 'extract') loadExtractCards();
  if (name === 'review') initReview();
}

function handleHash() {
  const hash = location.hash.slice(1) || 'merge';
  if (hash.startsWith('review/')) {
    const cardId = decodeURIComponent(hash.slice(7));
    showSection('review');
    reviewJumpTo(cardId);
  } else {
    showSection(hash);
  }
}

window.addEventListener('hashchange', handleHash);

/* ---- Merge ---- */
async function loadMergePairs() {
  const resp = await fetch('/api/merge/pairs');
  const data = await resp.json();
  const grid = document.getElementById('pairs-grid');
  const countEl = document.getElementById('merge-pair-count');
  grid.innerHTML = '';
  countEl.textContent = data.pairs.length + ' pair' + (data.pairs.length !== 1 ? 's' : '') + ' detected';

  data.pairs.forEach(pair => {
    const card = document.createElement('div');
    card.className = 'pair-card' + (pair.merged ? ' merged' : '');
    const imgs = document.createElement('div');
    imgs.className = 'pair-images';

    if (pair.merged) {
      const img = document.createElement('img');
      img.className = 'merged-img';
      img.src = '/output-images/' + encodeURIComponent(pair.front);
      imgs.appendChild(img);
    } else {
      const frontImg = document.createElement('img');
      frontImg.src = '/images/' + encodeURIComponent(pair.front);
      const backImg = document.createElement('img');
      backImg.src = '/images/' + encodeURIComponent(pair.back);
      imgs.appendChild(frontImg);
      imgs.appendChild(backImg);
    }

    const name = document.createElement('div');
    name.className = 'pair-name';
    name.innerHTML = pair.name + (pair.merged ? ' <span class="status ok">&#10003; merged</span>' : '');

    card.appendChild(imgs);
    card.appendChild(name);
    grid.appendChild(card);
  });

  data.errors.forEach(err => {
    const card = document.createElement('div');
    card.className = 'pair-card error';
    const imgs = document.createElement('div');
    imgs.className = 'pair-images';
    const ph = document.createElement('div');
    ph.className = 'placeholder missing';
    ph.textContent = 'missing';
    imgs.appendChild(ph);
    const name = document.createElement('div');
    name.className = 'pair-name';
    name.style.color = '#e74c3c';
    name.textContent = err;
    card.appendChild(imgs);
    card.appendChild(name);
    grid.appendChild(card);
  });
}

async function triggerMerge() {
  const btn = document.getElementById('merge-btn');
  btn.disabled = true;
  btn.textContent = 'Merging...';

  const resp = await fetch('/api/merge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  const data = await resp.json();

  const summary = document.getElementById('merge-summary');
  summary.style.display = 'block';
  let parts = [];
  if (data.ok > 0) parts.push('<span class="ok">&#10003; ' + data.ok + ' merged</span>');
  if (data.skipped > 0) parts.push('<span class="skip">' + data.skipped + ' skipped</span>');
  if (data.errors.length > 0) parts.push('<span class="err">&#10007; ' + data.errors.length + ' error(s)</span>');
  summary.innerHTML = parts.join(' &middot; ');

  btn.disabled = false;
  btn.textContent = 'Merge All';
  loadMergePairs();
}

/* ---- Extract ---- */
let extractPollInterval = null;

async function loadExtractCards() {
  const resp = await fetch('/api/extract/cards');
  const data = await resp.json();
  const countEl = document.getElementById('extract-count');
  const pending = data.cards.filter(c => c.status === 'pending').length;
  const done = data.cards.filter(c => c.status === 'done').length;
  countEl.textContent = data.cards.length + ' card' + (data.cards.length !== 1 ? 's' : '') + ' (' + done + ' done, ' + pending + ' pending)';

  renderExtractList(data.cards.map(c => ({ ...c, icon: c.status === 'done' ? 'done' : 'queued' })));

  // Check if already running
  const statusResp = await fetch('/api/extract/status');
  const status = await statusResp.json();
  if (status.status === 'running' || status.status === 'cancelling') {
    startExtractPolling();
  }
}

function renderExtractList(cards) {
  const list = document.getElementById('extract-card-list');
  list.innerHTML = '';
  cards.forEach(c => {
    const item = document.createElement('div');
    const cls = c.icon === 'done' ? '' : c.icon === 'progress' ? ' in-progress' : c.icon === 'error' ? '' : ' queued';
    item.className = 'card-item' + cls;

    const iconMap = { done: '&#10003;', error: '&#10007;', progress: '&#9679;', queued: '&#9675;' };
    item.innerHTML =
      '<span class="icon ' + c.icon + '">' + (iconMap[c.icon] || '') + '</span>' +
      '<span class="name">' + (c.name || c.card_id || '') + '</span>' +
      '<span class="status-text">' + (c.statusText || c.status || '') + '</span>' +
      (c.icon === 'done' ? '<span class="review-link" onclick="location.hash=\\'review/' + encodeURIComponent(c.name || c.card_id || '') + '\\'">Review &rarr;</span>' : '');

    list.appendChild(item);
  });
}

async function triggerExtract() {
  const force = document.getElementById('force-extract').checked;
  const resp = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force: force }),
  });
  const data = await resp.json();
  if (data.status === 'already_running') return;

  startExtractPolling();
}

function startExtractPolling() {
  document.getElementById('extract-btn').style.display = 'none';
  document.getElementById('cancel-btn').style.display = '';
  document.getElementById('extract-summary').style.display = 'flex';

  if (extractPollInterval) clearInterval(extractPollInterval);
  extractPollInterval = setInterval(pollExtractStatus, 1500);
  pollExtractStatus();
}

async function pollExtractStatus() {
  const resp = await fetch('/api/extract/status');
  const status = await resp.json();

  // Update summary
  const summary = document.getElementById('extract-summary');
  summary.innerHTML =
    '<span>' + status.done.length + ' done</span>' +
    (status.current ? '<span>1 in progress</span>' : '') +
    '<span>' + status.queue.length + ' queued</span>' +
    (status.errors.length > 0 ? '<span style="color:#e74c3c;">' + status.errors.length + ' error(s)</span>' : '');

  // Update current card
  const currentEl = document.getElementById('current-card');
  if (status.current) {
    currentEl.style.display = '';
    document.getElementById('current-name').textContent = status.current.card_id;
    const steps = ['ocr_front', 'ocr_back', 'date_verify', 'llm_extract'];
    const currentIdx = steps.indexOf(status.current.step);
    document.querySelectorAll('.pipeline-step').forEach((el, i) => {
      el.className = 'pipeline-step' + (i < currentIdx ? ' done' : i === currentIdx ? ' active' : '');
    });
  } else {
    currentEl.style.display = 'none';
  }

  // Update card list
  let cards = [];
  status.done.forEach(name => cards.push({ name: name, icon: 'done', statusText: 'Done', status: 'done' }));
  if (status.current) cards.push({ name: status.current.card_id, icon: 'progress', statusText: status.current.step.replace('_', ' '), status: 'progress' });
  status.errors.forEach(e => cards.push({ name: e.card_id, icon: 'error', statusText: e.reason, status: 'error' }));
  status.queue.forEach(name => cards.push({ name: name, icon: 'queued', statusText: 'Queued', status: 'queued' }));
  renderExtractList(cards);

  // Check if done
  if (status.status === 'idle' || status.status === 'cancelled') {
    clearInterval(extractPollInterval);
    extractPollInterval = null;
    document.getElementById('extract-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = 'none';
    if (status.status === 'cancelled') {
      document.getElementById('extract-summary').innerHTML += '<span style="color:#e67e22;"> (cancelled)</span>';
    }
  }
}

async function cancelExtract() {
  await fetch('/api/extract/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
}

/* ---- Review ---- */
let reviewCards = [];
let reviewIndex = 0;
let reviewCurrentCard = null;
let reviewCurrentSide = 'back';
let reviewInitialized = false;

async function initReview() {
  const resp = await fetch('/api/cards');
  reviewCards = await resp.json();
  if (reviewCards.length === 0) {
    document.getElementById('no-cards').style.display = '';
    document.querySelector('.review-main').style.display = 'none';
    document.querySelector('.review-header').style.display = 'none';
    return;
  }
  document.getElementById('no-cards').style.display = 'none';
  document.querySelector('.review-main').style.display = '';
  document.querySelector('.review-header').style.display = '';
  if (!reviewInitialized) {
    reviewInitialized = true;
    await loadReviewCard(0);
  }
}

function reviewJumpTo(cardId) {
  const idx = reviewCards.indexOf(cardId);
  if (idx >= 0) loadReviewCard(idx);
}

async function loadReviewCard(index) {
  reviewIndex = index;
  const id = reviewCards[index];
  const resp = await fetch('/api/cards/' + encodeURIComponent(id));
  reviewCurrentCard = await resp.json();

  document.getElementById('review-counter').textContent = (index + 1) + ' / ' + reviewCards.length;
  document.getElementById('prev-btn').disabled = index === 0;
  document.getElementById('next-btn').disabled = index === reviewCards.length - 1;

  const p = reviewCurrentCard.data.person || {};
  document.getElementById('f-first_name').value = p.first_name || '';
  document.getElementById('f-last_name').value = p.last_name || '';
  document.getElementById('f-birth_date').value = p.birth_date || '';
  document.getElementById('f-birth_place').value = p.birth_place || '';
  document.getElementById('f-death_date').value = p.death_date || '';
  document.getElementById('f-death_place').value = p.death_place || '';
  document.getElementById('f-age_at_death').value = p.age_at_death != null ? p.age_at_death : '';

  document.getElementById('spouses-list').innerHTML = '';
  (p.spouses || []).forEach(name => addSpouseInput(name));
  if (!p.spouses || p.spouses.length === 0) addSpouseInput('');

  const notesList = document.getElementById('notes-list');
  notesList.innerHTML = '';
  (reviewCurrentCard.data.notes || []).forEach(note => {
    const li = document.createElement('li');
    li.textContent = note;
    notesList.appendChild(li);
  });

  const btn = document.getElementById('approve-btn');
  btn.textContent = 'Approve';
  btn.classList.remove('btn-success');
  btn.classList.add('btn-primary');

  showSide('back');
}

function addSpouseInput(value) {
  const container = document.getElementById('spouses-list');
  const div = document.createElement('div');
  div.className = 'spouse-entry';
  const input = document.createElement('input');
  input.value = value;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = '\\u00d7';
  btn.onclick = function() { div.remove(); };
  div.appendChild(input);
  div.appendChild(btn);
  container.appendChild(div);
}

function getSpousesFromForm() {
  const inputs = document.querySelectorAll('#spouses-list .spouse-entry input');
  const names = [];
  inputs.forEach(input => { const v = input.value.trim(); if (v) names.push(v); });
  return names;
}

function showSide(side) {
  reviewCurrentSide = side;
  const img = document.getElementById('card-image');
  const noImg = document.getElementById('no-image');
  const src = side === 'front' ? reviewCurrentCard.front_image : reviewCurrentCard.back_image;

  document.getElementById('front-btn').classList.toggle('active', side === 'front');
  document.getElementById('back-btn').classList.toggle('active', side === 'back');

  if (src) {
    img.src = '/images/' + encodeURIComponent(src);
    img.style.display = '';
    noImg.style.display = 'none';
  } else {
    img.style.display = 'none';
    noImg.style.display = '';
  }
}

function reviewNavigate(delta) {
  const next = reviewIndex + delta;
  if (next >= 0 && next < reviewCards.length) loadReviewCard(next);
}

async function approveCard() {
  const ageRaw = document.getElementById('f-age_at_death').value.trim();
  const updated = {
    person: {
      first_name: document.getElementById('f-first_name').value.trim() || null,
      last_name: document.getElementById('f-last_name').value.trim() || null,
      birth_date: document.getElementById('f-birth_date').value.trim() || null,
      birth_place: document.getElementById('f-birth_place').value.trim() || null,
      death_date: document.getElementById('f-death_date').value.trim() || null,
      death_place: document.getElementById('f-death_place').value.trim() || null,
      age_at_death: ageRaw ? parseInt(ageRaw, 10) : null,
      spouses: getSpousesFromForm(),
    },
    notes: reviewCurrentCard.data.notes || [],
    source: {},
  };

  await fetch('/api/cards/' + encodeURIComponent(reviewCards[reviewIndex]), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updated),
  });

  const btn = document.getElementById('approve-btn');
  btn.textContent = 'Saved!';
  btn.classList.remove('btn-primary');
  btn.classList.add('btn-success');
}

/* ---- Init ---- */
handleHash();
</script>
</body>
</html>
"""
```

- [ ] **Step 4: Run all server tests**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add full SPA HTML with merge, extract, and review sections"
```

---

### Task 7: Update main.py to start the web server

Change `main.py` so the default command starts the web server instead of running the full pipeline.

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Update main.py**

Replace the contents of `src/main.py`:

```python
import argparse
from pathlib import Path
import webbrowser

import ollama

from src.merge import find_pairs, merge_all
from src.extract import extract_all
from src.server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Memorial card processing pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["merge", "extract", "all", "serve"],
        help="Which phase to run (default: serve)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all pairs, even if output already exists",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    text_dir = output_dir / "text"
    json_dir = output_dir / "json"
    conflicts_dir = output_dir / "date_conflicts"
    prompt_path = script_dir / "prompts" / "extract_person.txt"

    # --- Serve (web UI) ---
    if args.command == "serve":
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        json_dir.mkdir(exist_ok=True)

        server = make_server(json_dir, input_dir, output_dir)
        port = server.server_address[1]
        url = f"http://localhost:{port}"
        print(f"Memorial Card Digitizer running at {url}")
        print("Press Ctrl+C to stop.")
        webbrowser.open(url)
        server.serve_forever()
        return

    if not input_dir.exists():
        input_dir.mkdir()
        print(f"Created {input_dir}/ — drop your scans there and run again.")
        return

    pairs, pairing_errors = find_pairs(input_dir)

    if not pairs and not pairing_errors:
        print("No scans found in input/. Drop front + back JPEG pairs there and run again.")
        return

    output_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)
    json_dir.mkdir(exist_ok=True)

    total = len(pairs)
    print(f"Found {total} pair{'s' if total != 1 else ''} in input/")

    all_errors: list[str] = list(pairing_errors)
    ok_count = 0
    merge_skipped = 0
    text_count = 0
    verify_count = 0
    interpret_count = 0
    extract_skipped = 0

    # --- Merge phase ---
    if args.command in ("merge", "all"):
        print("\\n--- Merge ---")
        ok_count, merge_skipped, merge_errors = merge_all(pairs, output_dir, force=args.force)
        all_errors.extend(merge_errors)

    # --- Extract phase ---
    if args.command in ("extract", "all"):
        prompt_template = None
        if prompt_path.exists():
            prompt_template = prompt_path.read_text()
        else:
            print(f"Warning: prompt template not found at {prompt_path} — skipping interpretation")

        ollama_available = False
        if prompt_template:
            try:
                ollama.list()
                ollama_available = True
            except Exception as e:
                print(f"Warning: Ollama not reachable ({e}) — skipping LLM steps")

        print("\\n--- Extract ---")
        text_count, verify_count, interpret_count, extract_skipped, _, extract_errors = extract_all(
            pairs, text_dir, json_dir, conflicts_dir,
            prompt_template, ollama_available, force=args.force,
        )
        all_errors.extend(extract_errors)

    # --- Summary ---
    parts = []
    if args.command in ("merge", "all"):
        skip_note = f" ({merge_skipped} skipped)" if merge_skipped else ""
        parts.append(f"{ok_count} merged{skip_note}")
    if args.command in ("extract", "all"):
        skip_note = f" ({extract_skipped} skipped)" if extract_skipped else ""
        parts.append(f"{text_count} text extracted{skip_note}")
        parts.append(f"{verify_count} date{'s' if verify_count != 1 else ''} corrected")
        parts.append(f"{interpret_count} interpreted")
    parts.append(f"{len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    print(f"\\nDone: {', '.join(parts)}")

    if all_errors:
        print(f"\\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests to verify nothing is broken**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: change default command to serve (web UI)"
```

---

### Task 8: Update VS Code launch configurations

Update the debug configurations to reflect the new `serve` command and remove the old `review` command.

**Files:**
- Modify: `.vscode/launch.json`

- [ ] **Step 1: Read the current launch.json**

Read `.vscode/launch.json` to understand the existing configurations.

- [ ] **Step 2: Update launch.json**

Replace the `review` configuration with a `serve` configuration. Update the default configuration (if it runs `all`) to note that `serve` is now the default. The `serve` configuration should use:

```json
{
    "name": "Serve (Web UI)",
    "type": "debugpy",
    "request": "launch",
    "module": "src.main",
    "args": ["serve"]
}
```

Remove the old `Review` configuration since `review` is no longer a valid CLI command.

- [ ] **Step 3: Commit**

```bash
git add .vscode/launch.json
git commit -m "feat: update VS Code launch config for serve command"
```

---

### Task 9: Final integration test

Run the full test suite and verify everything works together.

**Files:**
- No new files

- [ ] **Step 1: Run all tests**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify the server starts**

Run: `cd /Users/timrijckaert/Documents/memorial-service && timeout 3 python -m src.main serve 2>&1 || true`
Expected: Output includes "Memorial Card Digitizer running at http://localhost:" (server starts, then timeout kills it)

- [ ] **Step 3: Verify CLI commands still work**

Run: `cd /Users/timrijckaert/Documents/memorial-service && python -m src.main merge --help`
Expected: Shows help text with `merge` command description

- [ ] **Step 4: Clean up .superpowers brainstorm files if present**

If `.superpowers/` directory was created during brainstorming, add it to `.gitignore`:

Check if `.superpowers` is in `.gitignore`. If not, add it.

- [ ] **Step 5: Commit any cleanup**

```bash
git add .gitignore
git commit -m "chore: add .superpowers to gitignore"
```
