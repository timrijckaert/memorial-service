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
