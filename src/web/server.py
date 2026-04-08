# src/web/server.py
"""HTTP server for the memorial card web application."""

import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from src.extraction import make_backend
from src.export import run_export
from src.images.stitching import stitch_pair
from src.naming import derive_filename
from src.web.match_state import MatchState
from src.review import list_cards, load_card, save_card
from src.web.worker import ExtractionWorker

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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

    def _serve_file(self, base_dir: Path, filename: str):
        """Serve a file from base_dir with path traversal protection."""
        file_path = (base_dir / filename).resolve()
        if not str(file_path).startswith(str(base_dir.resolve())):
            self._send_error(403, "Forbidden")
            return
        if not file_path.exists():
            self._send_error(404, "Not found")
            return

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = file_path.read_bytes()
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
            self._serve_file(_STATIC_DIR, "index.html")
        elif self.path.startswith("/static/"):
            filename = unquote(self.path[len("/static/"):])
            self._serve_file(_STATIC_DIR, filename)
        elif self.path == "/api/cards":
            self._send_json(list_cards(json_dir))
        elif self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            result = load_card(card_id, json_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                result["derived_name"] = derive_filename(result["data"])
                self._send_json(result)
        elif self.path.startswith("/images/"):
            filename = unquote(self.path[len("/images/"):])
            self._serve_file(input_dir, filename)
        elif self.path.startswith("/output-images/"):
            filename = unquote(self.path[len("/output-images/"):])
            self._serve_file(output_dir, filename)
        elif self.path == "/api/match/scan":
            result = self.server.match_state.scan()
            self._send_json(result)
        elif self.path == "/api/match/state":
            self._send_json(self.server.match_state.get_snapshot())
        elif self.path == "/api/extract/status":
            self._send_json(self.server.worker.get_status().to_dict())
        elif self.path == "/api/extract/cards":
            pairs, singles = self.server.match_state.get_confirmed_items()
            cards = []
            for front, back in pairs:
                json_path = json_dir / f"{front.stem}.json"
                has_json = json_path.exists()
                derived_name = None
                if has_json:
                    card_data = json.loads(json_path.read_text())
                    derived_name = derive_filename(card_data)
                cards.append({
                    "name": front.stem,
                    "front": front.name,
                    "back": back.name,
                    "status": "done" if has_json else "pending",
                    "derived_name": derived_name,
                })
            for single in singles:
                json_path = json_dir / f"{single.stem}.json"
                has_json = json_path.exists()
                derived_name = None
                if has_json:
                    card_data = json.loads(json_path.read_text())
                    derived_name = derive_filename(card_data)
                cards.append({
                    "name": single.stem,
                    "front": single.name,
                    "back": None,
                    "status": "done" if has_json else "pending",
                    "derived_name": derived_name,
                })
            self._send_json({"cards": cards})
        elif self.path == "/api/export/count":
            count = len(list(json_dir.glob("*.json")))
            self._send_json({"count": count})
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
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir
        json_dir = self.server.json_dir

        if self.path == "/api/match/confirm":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.confirm(data["image_a"], data["image_b"])
            self._send_json(result)
        elif self.path == "/api/match/confirm-all":
            result = self.server.match_state.confirm_all()
            self._send_json(result)
        elif self.path == "/api/match/unmatch":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.unmatch(data["image_a"], data["image_b"])
            self._send_json(result)
        elif self.path == "/api/match/pair":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.manual_pair(data["image_a"], data["image_b"])
            self._send_json(result)
        elif self.path == "/api/match/single":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.mark_single(data["filename"])
            self._send_json(result)
        elif self.path == "/api/match/swap":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.swap(data["image_a"], data["image_b"])
            self._send_json(result)
        elif self.path == "/api/match/scores":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.get_scores_for(data["filename"])
            self._send_json(result)
        elif self.path == "/api/extract":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            cards_filter = options.get("cards", None)
            pairs, singles = self.server.match_state.get_confirmed_items()
            all_items = pairs + [(s, None) for s in singles]
            if cards_filter:
                card_set = set(cards_filter)
                all_items = [(f, b) for f, b in all_items if f.stem in card_set]
            text_dir = output_dir / "text"
            text_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)
            conflicts_dir = output_dir / "date_conflicts"

            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            user_template_path = prompts_dir / "extract_person_user.txt"
            system_prompt = None
            user_template = None
            if system_prompt_path.exists() and user_template_path.exists():
                system_prompt = system_prompt_path.read_text()
                user_template = user_template_path.read_text()

            backend = self.server.backend if system_prompt else None

            started = self.server.worker.start(
                all_items, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, backend,
            )
            if started:
                self._send_json({"status": "started"})
            else:
                self._send_json({"status": "already_running"}, 409)
        elif self.path == "/api/extract/cancel":
            self.server.worker.cancel()
            self._send_json({"status": "cancelling"})
        elif self.path == "/api/export":
            result = run_export(json_dir, input_dir, output_dir)
            self._send_json(result)
        else:
            self._send_error(404, "Not found")


def make_server(
    json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0
) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    server.worker = ExtractionWorker()
    server.match_state = MatchState(input_dir, output_dir)
    config_path = input_dir.parent / "config.json"
    server.backend = make_backend(config_path)
    return server
