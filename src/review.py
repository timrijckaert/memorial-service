import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

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


class ReviewHandler(BaseHTTPRequestHandler):
    """HTTP handler for the review UI API and static assets."""

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
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

    def do_GET(self):
        json_dir = self.server.json_dir
        input_dir = self.server.input_dir

        if self.path == "/":
            self._serve_html()
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

    def _serve_html(self):
        body = REVIEW_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_image(self, input_dir: Path, filename: str):
        # Prevent path traversal
        image_path = (input_dir / filename).resolve()
        if not str(image_path).startswith(str(input_dir.resolve())):
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


# Placeholder — replaced in Task 3
REVIEW_HTML = "<html><body>Review UI</body></html>"


def make_server(json_dir: Path, input_dir: Path, port: int = 0) -> HTTPServer:
    """Create an HTTPServer with the review handler, bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), ReviewHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    return server
