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


REVIEW_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memorial Card Review</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #333; }
  .header { display: flex; align-items: center; justify-content: space-between; padding: 12px 24px; background: #fff; border-bottom: 1px solid #ddd; }
  .header h1 { font-size: 18px; }
  .nav { display: flex; gap: 8px; align-items: center; }
  .nav button { padding: 6px 16px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; }
  .nav button:hover { background: #eee; }
  .nav button:disabled { opacity: 0.4; cursor: default; }
  .counter { font-size: 14px; color: #666; min-width: 80px; text-align: center; }
  .main { display: flex; height: calc(100vh - 53px); }
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
  .approve-btn { width: 100%; padding: 12px; margin-top: 24px; background: #4a90d9; color: #fff; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
  .approve-btn:hover { background: #3a7bc8; }
  .approve-btn.saved { background: #5cb85c; }
  .no-image { color: #888; font-style: italic; }
</style>
</head>
<body>
<div class="header">
  <h1>Memorial Card Review</h1>
  <div class="nav">
    <button id="prev-btn" onclick="navigate(-1)">&larr; Previous</button>
    <span id="counter" class="counter">-</span>
    <button id="next-btn" onclick="navigate(1)">Next &rarr;</button>
  </div>
</div>
<div class="main">
  <div class="image-panel">
    <div class="image-toggle">
      <button id="front-btn" class="active" onclick="showSide('front')">Front</button>
      <button id="back-btn" onclick="showSide('back')">Back</button>
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
    <div class="form-group"><label>Spouse</label><input id="f-spouse"></div>
    <div class="section-title">Parents</div>
    <div class="form-group"><label>Father</label><input id="f-father"></div>
    <div class="form-group"><label>Mother</label><input id="f-mother"></div>
    <div class="section-title">Notes (from LLM)</div>
    <ul id="notes-list" class="notes-list"></ul>
    <button id="approve-btn" class="approve-btn" onclick="approveCard()">Approve</button>
  </div>
</div>
<script>
let cards = [];
let currentIndex = 0;
let currentCard = null;
let currentSide = "front";

async function init() {
  const resp = await fetch("/api/cards");
  cards = await resp.json();
  if (cards.length === 0) {
    document.getElementById("counter").textContent = "No cards";
    return;
  }
  await loadCard(0);
}

async function loadCard(index) {
  currentIndex = index;
  const id = cards[index];
  const resp = await fetch("/api/cards/" + encodeURIComponent(id));
  currentCard = await resp.json();

  document.getElementById("counter").textContent = (index + 1) + " / " + cards.length;
  document.getElementById("prev-btn").disabled = index === 0;
  document.getElementById("next-btn").disabled = index === cards.length - 1;

  const p = currentCard.data.person || {};
  document.getElementById("f-first_name").value = p.first_name || "";
  document.getElementById("f-last_name").value = p.last_name || "";
  document.getElementById("f-birth_date").value = p.birth_date || "";
  document.getElementById("f-birth_place").value = p.birth_place || "";
  document.getElementById("f-death_date").value = p.death_date || "";
  document.getElementById("f-death_place").value = p.death_place || "";
  document.getElementById("f-age_at_death").value = p.age_at_death != null ? p.age_at_death : "";
  document.getElementById("f-spouse").value = p.spouse || "";

  const parents = p.parents || {};
  document.getElementById("f-father").value = parents.father || "";
  document.getElementById("f-mother").value = parents.mother || "";

  const notesList = document.getElementById("notes-list");
  notesList.innerHTML = "";
  (currentCard.data.notes || []).forEach(function(note) {
    const li = document.createElement("li");
    li.textContent = note;
    notesList.appendChild(li);
  });

  const btn = document.getElementById("approve-btn");
  btn.textContent = "Approve";
  btn.classList.remove("saved");

  showSide("front");
}

function showSide(side) {
  currentSide = side;
  const img = document.getElementById("card-image");
  const noImg = document.getElementById("no-image");
  const src = side === "front" ? currentCard.front_image : currentCard.back_image;

  document.getElementById("front-btn").classList.toggle("active", side === "front");
  document.getElementById("back-btn").classList.toggle("active", side === "back");

  if (src) {
    img.src = "/images/" + encodeURIComponent(src);
    img.style.display = "";
    noImg.style.display = "none";
  } else {
    img.style.display = "none";
    noImg.style.display = "";
  }
}

function navigate(delta) {
  const next = currentIndex + delta;
  if (next >= 0 && next < cards.length) {
    loadCard(next);
  }
}

async function approveCard() {
  const ageRaw = document.getElementById("f-age_at_death").value.trim();
  const parents_father = document.getElementById("f-father").value.trim() || null;
  const parents_mother = document.getElementById("f-mother").value.trim() || null;
  const parents = (parents_father || parents_mother) ? { father: parents_father, mother: parents_mother } : null;

  const updated = {
    person: {
      first_name: document.getElementById("f-first_name").value.trim() || null,
      last_name: document.getElementById("f-last_name").value.trim() || null,
      birth_date: document.getElementById("f-birth_date").value.trim() || null,
      birth_place: document.getElementById("f-birth_place").value.trim() || null,
      death_date: document.getElementById("f-death_date").value.trim() || null,
      death_place: document.getElementById("f-death_place").value.trim() || null,
      age_at_death: ageRaw ? parseInt(ageRaw, 10) : null,
      spouse: document.getElementById("f-spouse").value.trim() || null,
      parents: parents,
    },
    notes: currentCard.data.notes || [],
    source: {},
  };

  await fetch("/api/cards/" + encodeURIComponent(cards[currentIndex]), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updated),
  });

  const btn = document.getElementById("approve-btn");
  btn.textContent = "Saved!";
  btn.classList.add("saved");
}

init();
</script>
</body>
</html>
"""


def make_server(json_dir: Path, input_dir: Path, port: int = 0) -> HTTPServer:
    """Create an HTTPServer with the review handler, bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), ReviewHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    return server
