# Export Pipeline & Fuzzy Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived filename utility, an Export phase that writes stitched images + consolidated JSON to `output/`, show derived names in the Extract/Review tabs, and rename `input/` files to simulate messy real-world scanner output.

**Architecture:** A pure `derive_filename()` function in `src/naming.py` computes canonical names from card data. A new `POST /api/export` endpoint iterates extracted card JSONs, stitches images, and writes `output/memorial_cards.json`. The frontend gets an Export button in the nav bar showing the count of exportable cards. Input files are renamed once to test fuzzy matching.

**Tech Stack:** Python 3, PIL/Pillow, stdlib `http.server`, vanilla JS/HTML/CSS

---

### Task 1: Derived Filename Utility — `src/naming.py`

**Files:**
- Create: `src/naming.py`
- Create: `tests/test_naming.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_naming.py`:

```python
# tests/test_naming.py
from src.naming import format_dutch_date, derive_filename


def test_format_dutch_date_januari():
    assert format_dutch_date("1913-01-21") == "21 januari 1913"


def test_format_dutch_date_december():
    assert format_dutch_date("1980-12-15") == "15 december 1980"


def test_format_dutch_date_mei():
    assert format_dutch_date("1927-05-04") == "04 mei 1927"


def test_format_dutch_date_strips_leading_zero_not():
    # Convention keeps leading zero: "05 januari" not "5 januari"
    assert format_dutch_date("1898-01-05") == "05 januari 1898"


def test_derive_filename_all_fields():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "birth_place": "Kerksken",
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje 21 december 1913"


def test_derive_filename_no_birth_place():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "birth_place": None,
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus bidprentje 21 december 1913"


def test_derive_filename_no_death_date():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "birth_place": "Kerksken",
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje"


def test_derive_filename_only_last_name():
    card = {
        "person": {
            "first_name": None,
            "last_name": "Meganck",
            "birth_place": None,
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck bidprentje"


def test_derive_filename_empty_person():
    card = {"person": {}}
    assert derive_filename(card) == "bidprentje"


def test_derive_filename_missing_person_key():
    card = {}
    assert derive_filename(card) == "bidprentje"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.naming'`

- [ ] **Step 3: Implement `src/naming.py`**

Create `src/naming.py`:

```python
# src/naming.py
"""Derive canonical filenames from extracted card data."""

_DUTCH_MONTHS = {
    1: "januari", 2: "februari", 3: "maart", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "augustus",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}


def format_dutch_date(iso_date: str) -> str:
    """Convert ISO date 'YYYY-MM-DD' to 'DD month YYYY' with Dutch month names."""
    year, month, day = iso_date.split("-")
    return f"{day} {_DUTCH_MONTHS[int(month)]} {year}"


def derive_filename(card: dict) -> str:
    """Build a canonical filename from card data.

    Convention: Surname Firstname Birthplace bidprentje DD month YYYY
    Missing fields are omitted. Always includes 'bidprentje'.
    """
    person = card.get("person", {})
    parts = []

    if person.get("last_name"):
        parts.append(person["last_name"])
    if person.get("first_name"):
        parts.append(person["first_name"])
    if person.get("birth_place"):
        parts.append(person["birth_place"])

    parts.append("bidprentje")

    if person.get("death_date"):
        parts.append(format_dutch_date(person["death_date"]))

    return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_naming.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/naming.py tests/test_naming.py
git commit -m "feat: add derive_filename utility for canonical card naming"
```

---

### Task 2: Export Backend — `POST /api/export`

**Files:**
- Create: `src/export.py`
- Create: `tests/test_export.py`
- Modify: `src/web/server.py:132-219` (add export endpoint to `do_POST`)
- Modify: `src/web/server.py:54-107` (add export count to `do_GET`)

- [ ] **Step 1: Write the failing tests for the export function**

Create `tests/test_export.py`:

```python
# tests/test_export.py
import json
from pathlib import Path

from PIL import Image

from src.export import run_export


def _make_image(path, width=100, height=150):
    Image.new("RGB", (width, height)).save(path, "JPEG")


def _make_card_json(json_dir, stem, person, front_image, back_image=None):
    data = {
        "person": person,
        "notes": ["test note"],
        "source": {
            "front_text_file": f"{stem}_front.txt",
            "back_text_file": f"{stem}_back.txt" if back_image else None,
            "front_image_file": front_image,
            "back_image_file": back_image,
        },
    }
    (json_dir / f"{stem}.json").write_text(json.dumps(data))


def test_export_single_card_with_pair(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    _make_image(input_dir / "front.jpeg")
    _make_image(input_dir / "back.jpeg")
    _make_card_json(
        json_dir, "front",
        person={
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "birth_place": "Kerksken",
            "death_date": "1913-12-21",
            "death_place": "Kerksken",
            "birth_date": "1850-03-10",
            "age_at_death": 63,
            "spouses": [],
        },
        front_image="front.jpeg",
        back_image="back.jpeg",
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1

    # Check stitched image exists
    expected_name = "Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg"
    assert (output_dir / expected_name).exists()

    # Check consolidated JSON
    memorial = json.loads((output_dir / "memorial_cards.json").read_text())
    key = "Meganck Dominicus Kerksken bidprentje 21 december 1913"
    assert key in memorial
    assert memorial[key]["first_name"] == "Dominicus"
    assert memorial[key]["last_name"] == "Meganck"
    assert memorial[key]["notes"] == ["test note"]
    # No source metadata in export
    assert "source" not in memorial[key]
    # Flattened person (no nested "person" key)
    assert "person" not in memorial[key]


def test_export_single_image_no_back(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    _make_image(input_dir / "single.jpeg")
    _make_card_json(
        json_dir, "single",
        person={
            "first_name": "Frans",
            "last_name": "Van den Bruele",
            "birth_place": "Haaltert",
            "death_date": "1898-01-05",
            "death_place": None,
            "birth_date": None,
            "age_at_death": None,
            "spouses": [],
        },
        front_image="single.jpeg",
        back_image=None,
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1
    expected_name = "Van den Bruele Frans Haaltert bidprentje 05 januari 1898.jpeg"
    assert (output_dir / expected_name).exists()


def test_export_filename_collision(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    person = {
        "first_name": "Jan",
        "last_name": "Pieters",
        "birth_place": None,
        "death_date": "1950-06-01",
        "death_place": None,
        "birth_date": None,
        "age_at_death": None,
        "spouses": [],
    }

    _make_image(input_dir / "card1.jpeg")
    _make_card_json(json_dir, "card1", person=person, front_image="card1.jpeg")

    _make_image(input_dir / "card2.jpeg")
    _make_card_json(json_dir, "card2", person=person, front_image="card2.jpeg")

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 2
    base = "Pieters Jan bidprentje 01 juni 1950"
    assert (output_dir / f"{base}.jpeg").exists()
    assert (output_dir / f"{base} (2).jpeg").exists()


def test_export_empty_json_dir(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 0
    assert not (output_dir / "memorial_cards.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.export'`

- [ ] **Step 3: Implement `src/export.py`**

Create `src/export.py`:

```python
# src/export.py
"""Export phase: stitch images and write consolidated memorial_cards.json."""

import json
import shutil
from pathlib import Path

from src.images.stitching import stitch_pair
from src.naming import derive_filename


def run_export(json_dir: Path, input_dir: Path, output_dir: Path) -> dict:
    """Export all extracted cards to output directory.

    For each card JSON in json_dir:
    - Stitch front+back images (or copy front if no back)
    - Write to output_dir/{derived_filename}.jpeg
    - Collect all cards into output_dir/memorial_cards.json

    Returns dict with 'exported' count.
    """
    card_files = sorted(json_dir.glob("*.json"))
    if not card_files:
        return {"exported": 0}

    consolidated = {}
    used_names: dict[str, int] = {}

    for card_path in card_files:
        data = json.loads(card_path.read_text())
        source = data.get("source", {})
        person = data.get("person", {})
        notes = data.get("notes", [])

        # Derive canonical filename
        base_name = derive_filename(data)

        # Handle collisions
        if base_name in used_names:
            used_names[base_name] += 1
            display_name = f"{base_name} ({used_names[base_name]})"
        else:
            used_names[base_name] = 1
            display_name = base_name

        # Stitch or copy image
        front_file = source.get("front_image_file")
        back_file = source.get("back_image_file")
        output_image = output_dir / f"{display_name}.jpeg"

        if front_file and back_file:
            front_path = input_dir / front_file
            back_path = input_dir / back_file
            if front_path.exists() and back_path.exists():
                stitch_pair(front_path, back_path, output_image)
            elif front_path.exists():
                shutil.copy2(front_path, output_image)
        elif front_file:
            front_path = input_dir / front_file
            if front_path.exists():
                shutil.copy2(front_path, output_image)

        # Build flattened entry for consolidated JSON
        entry = {**person, "notes": notes}
        consolidated[display_name] = entry

    # Write consolidated JSON
    memorial_path = output_dir / "memorial_cards.json"
    memorial_path.write_text(
        json.dumps(consolidated, indent=2, ensure_ascii=False)
    )

    return {"exported": len(consolidated)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_export.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat: add export function for stitched images and consolidated JSON"
```

---

### Task 3: Export Count API & Export Endpoint

**Files:**
- Modify: `src/web/server.py:54-107` (add `/api/export/count` to `do_GET`)
- Modify: `src/web/server.py:132-219` (add `/api/export` to `do_POST`)

- [ ] **Step 1: Write the failing test for the export count endpoint**

Add to `tests/test_server.py` (append at end of file):

```python
def test_export_count_returns_card_count(tmp_server):
    """GET /api/export/count returns number of extracted card JSONs."""
    # Create a card JSON to count
    import json
    card_data = {
        "person": {"first_name": "Test", "last_name": "Person"},
        "notes": [],
        "source": {"front_image_file": "test.jpeg", "back_image_file": None,
                    "front_text_file": "test.txt", "back_text_file": None},
    }
    (tmp_server.json_dir / "test_card.json").write_text(json.dumps(card_data))

    resp = _get(tmp_server, "/api/export/count")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert data["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_server.py::test_export_count_returns_card_count -v`
Expected: FAIL — 404

- [ ] **Step 3: Add the export count GET endpoint and export POST endpoint to server.py**

In `src/web/server.py`, add import at the top:

```python
from src.export import run_export
```

In `do_GET`, add before the final `else` clause:

```python
        elif self.path == "/api/export/count":
            count = len(list(json_dir.glob("*.json")))
            self._send_json({"count": count})
```

In `do_POST`, add before the final `else` clause:

```python
        elif self.path == "/api/export":
            result = run_export(json_dir, input_dir, output_dir)
            self._send_json(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_server.py::test_export_count_returns_card_count -v`
Expected: PASS

- [ ] **Step 5: Run all server tests to check for regressions**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/web/server.py
git commit -m "feat: add export count and export endpoints to server"
```

---

### Task 4: Export Button in Frontend

**Files:**
- Modify: `src/web/static/index.html:12-16` (add Export button to nav bar)
- Modify: `src/web/static/style.css:5-8` (add export button styling)
- Modify: `src/web/static/app.js:675-676` (add export functions + update init)

- [ ] **Step 1: Add Export button to the nav bar in index.html**

In `src/web/static/index.html`, replace the nav bar:

```html
<!-- Navigation -->
<nav class="nav-bar">
  <a class="nav-tab" href="#match" onclick="showSection('match')">Match</a>
  <a class="nav-tab" href="#extract" onclick="showSection('extract')">Extract</a>
  <a class="nav-tab" href="#review" onclick="showSection('review')">Review</a>
  <button id="export-btn" class="btn-export" onclick="triggerExport()" disabled>Export (0)</button>
</nav>
```

- [ ] **Step 2: Add CSS for the export button**

In `src/web/static/style.css`, add after the `.nav-tab.active` rule (after line 8):

```css
  .btn-export { margin-left: auto; margin-right: 12px; padding: 6px 16px; background: #27ae60; color: #fff; border: none; border-radius: 4px; font-weight: 600; font-size: 13px; cursor: pointer; align-self: center; }
  .btn-export:hover:not(:disabled) { background: #219a52; }
  .btn-export:disabled { opacity: 0.4; cursor: default; }
```

- [ ] **Step 3: Add export JavaScript functions in app.js**

Add before the `/* ---- Init ---- */` section at the end of `src/web/static/app.js`:

```javascript
/* ---- Export ---- */
async function updateExportCount() {
  const resp = await fetch('/api/export/count');
  const data = await resp.json();
  const btn = document.getElementById('export-btn');
  btn.textContent = 'Export (' + data.count + ')';
  btn.disabled = data.count === 0;
}

async function triggerExport() {
  const btn = document.getElementById('export-btn');
  btn.disabled = true;
  btn.textContent = 'Exporting...';

  const resp = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  const data = await resp.json();

  btn.textContent = 'Exported ' + data.exported + ' cards!';
  btn.classList.add('exported');
  setTimeout(function() {
    btn.classList.remove('exported');
    updateExportCount();
  }, 2000);
}
```

Also update the `showSection` function to refresh the export count when switching tabs. Add at the end of the `showSection` function body (before the closing `}`):

```javascript
  updateExportCount();
```

And update the init section to call `updateExportCount()` on load. In the `handleHash` function, add `updateExportCount()` after the `showSection` calls:

The simplest approach: add `updateExportCount();` as the last line in `handleHash()`, after the `showSection` calls.

- [ ] **Step 4: Test manually by running the server**

Run: `.venv/bin/python -m src.main`

Verify:
- Export button appears in the nav bar, right-aligned
- Shows "Export (0)" when no cards are extracted
- After extraction, count updates
- Clicking Export writes files and shows confirmation

- [ ] **Step 5: Commit**

```bash
git add src/web/static/index.html src/web/static/style.css src/web/static/app.js
git commit -m "feat: add Export button to nav bar with count and export trigger"
```

---

### Task 5: Show Derived Filename in Extract Tab

**Files:**
- Modify: `src/web/server.py:86-105` (add `derived_name` to `/api/extract/cards` response)
- Modify: `src/web/static/app.js:375-403` (use `derived_name` in `renderExtractList`)

- [ ] **Step 1: Add `derived_name` to the extract cards endpoint**

In `src/web/server.py`, add import for `derive_filename` at the top:

```python
from src.naming import derive_filename
```

In the `/api/extract/cards` handler (inside `do_GET`), update each card dict to include the derived name when a JSON exists. Replace the extract cards handler block:

```python
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
```

- [ ] **Step 2: Update `renderExtractList` in app.js to show derived name**

In `src/web/static/app.js`, in the `renderExtractList` function, update the card name display. Find the line that builds `cardName`:

```javascript
    const cardName = c.derived_name || c.name || c.card_id || '';
```

This replaces the existing line `const cardName = c.name || c.card_id || '';`.

- [ ] **Step 3: Also pass `derived_name` through the polling merge**

In `pollExtractStatus`, the merged cards are built from `allCards`. The `derived_name` is already on the `allCards` entries from the API. Update the merge to preserve it:

```javascript
    var w = workerMap[c.name];
    if (w) return { name: c.name, derived_name: c.derived_name, icon: w.icon, statusText: w.statusText, status: w.icon };
    return { name: c.name, derived_name: c.derived_name, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : c.status, status: c.status };
```

- [ ] **Step 4: Test manually**

Run: `.venv/bin/python -m src.main`

Verify: After extraction completes, cards in the Extract tab show the derived filename (e.g., "Meganck Dominicus Kerksken bidprentje 21 december 1913") instead of the raw filename stem.

- [ ] **Step 5: Commit**

```bash
git add src/web/server.py src/web/static/app.js
git commit -m "feat: show derived filename in Extract tab for completed cards"
```

---

### Task 6: Show Derived Filename in Review Tab

**Files:**
- Modify: `src/web/server.py:64-72` (add `derived_name` to `/api/cards/{id}` response)
- Modify: `src/web/static/index.html:60-66` (add derived name display in review header)
- Modify: `src/web/static/app.js:561-598` (compute and display derived name in review)

- [ ] **Step 1: Add derived_name to the card load endpoint**

In `src/web/server.py`, update the `/api/cards/{id}` handler in `do_GET` to include `derived_name`:

```python
        elif self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            result = load_card(card_id, json_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                result["derived_name"] = derive_filename(result["data"])
                self._send_json(result)
```

- [ ] **Step 2: Add derived name display in review header HTML**

In `src/web/static/index.html`, add a span to show the derived name in the review header. Update the review nav div:

```html
    <div class="review-header">
      <div class="review-nav">
        <button id="prev-btn" onclick="reviewNavigate(-1)">&larr; Previous</button>
        <span id="review-counter" class="review-counter">-</span>
        <button id="next-btn" onclick="reviewNavigate(1)">Next &rarr;</button>
      </div>
      <div id="review-derived-name" class="review-derived-name"></div>
    </div>
```

- [ ] **Step 3: Add CSS for the derived name display**

In `src/web/static/style.css`, add after the `.review-counter` rule:

```css
  .review-derived-name { font-size: 13px; color: #4a90d9; font-weight: 600; max-width: 50%; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

- [ ] **Step 4: Update JavaScript to show and live-update derived name**

In `src/web/static/app.js`, in `loadReviewCard`, add after setting the review counter:

```javascript
  document.getElementById('review-derived-name').textContent = reviewCurrentCard.derived_name || '';
```

Also add a function to recompute the derived name client-side when fields change, and call it from a shared helper. Add this near the review section:

```javascript
function computeDerivedName() {
  var months = {
    '01': 'januari', '02': 'februari', '03': 'maart', '04': 'april',
    '05': 'mei', '06': 'juni', '07': 'juli', '08': 'augustus',
    '09': 'september', '10': 'oktober', '11': 'november', '12': 'december'
  };
  var parts = [];
  var lastName = document.getElementById('f-last_name').value.trim();
  var firstName = document.getElementById('f-first_name').value.trim();
  var birthPlace = document.getElementById('f-birth_place').value.trim();
  var deathDate = document.getElementById('f-death_date').value.trim();

  if (lastName) parts.push(lastName);
  if (firstName) parts.push(firstName);
  if (birthPlace) parts.push(birthPlace);
  parts.push('bidprentje');

  if (deathDate && deathDate.match(/^\d{4}-\d{2}-\d{2}$/)) {
    var dateParts = deathDate.split('-');
    var month = months[dateParts[1]];
    if (month) parts.push(dateParts[2] + ' ' + month + ' ' + dateParts[0]);
  }

  document.getElementById('review-derived-name').textContent = parts.join(' ');
}
```

Then add `oninput="computeDerivedName()"` to the relevant form fields in `index.html`:

```html
<div class="form-group"><label>First Name</label><input id="f-first_name" oninput="computeDerivedName()"></div>
<div class="form-group"><label>Last Name</label><input id="f-last_name" oninput="computeDerivedName()"></div>
<div class="form-group"><label>Birth Place</label><input id="f-birth_place" oninput="computeDerivedName()"></div>
<div class="form-group"><label>Death Date (YYYY-MM-DD)</label><input id="f-death_date" oninput="computeDerivedName()"></div>
```

The Birth Date, Death Place, Age at Death, and Spouses fields do NOT need `oninput` since they don't affect the derived name.

- [ ] **Step 5: Test manually**

Run: `.venv/bin/python -m src.main`

Verify:
- Review tab shows the derived filename in the header
- Editing first name, last name, birth place, or death date updates the derived name live

- [ ] **Step 6: Commit**

```bash
git add src/web/server.py src/web/static/index.html src/web/static/style.css src/web/static/app.js
git commit -m "feat: show live-updating derived filename in Review tab header"
```

---

### Task 7: Rename Input Files to Fuzzy Variants

**Files:**
- Modify: `input/*.jpeg` (rename files)

This is a one-time manual renaming. The `input_backup/` directory already contains the originals.

- [ ] **Step 1: Create a rename script**

Create a temporary Python script `rename_inputs.py` in the project root:

```python
# rename_inputs.py
"""One-time script to rename input files to fuzzy variants for testing."""

import shutil
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent / "input"

# Mapping: original front name -> (new front name, new back name)
# Back images originally have " 1" suffix before .jpeg
RENAMES = {
    # === EXACT (keep as-is) ~10% — 2 pairs ===
    "Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg":
        ("Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg",
         "Meganck Dominicus Kerksken bidprentje 21 december 1913 1.jpeg"),

    "Vonck Maria Virginia Haaltert bidprentje 17 oktober 1936.jpeg":
        ("Vonck Maria Virginia Haaltert bidprentje 17 oktober 1936.jpeg",
         "Vonck Maria Virginia Haaltert bidprentje 17 oktober 1936 1.jpeg"),

    # === MINOR ~30% — 7 pairs: lowercase, abbreviated month, small typo ===
    "Van den Bruele Frans Haaltert  bidprentje 05 januari 1898.jpeg":
        ("van den bruele frans haaltert 05 jan 1898.jpeg",
         "van den bruele frans haaltert 05 jan 1898_back.jpeg"),

    "Van den Bruele Lybia Theresia Haaltert  bidprentje 11 december 1919.jpeg":
        ("vd bruele lybia theresia haaltert dec 1919.jpeg",
         "vd bruele lybia theresia haaltert dec 1919_achterkant.jpeg"),

    "Van den Bruele Stephanie  Haaltert  bidprentje 13 augustus 1938.jpeg":
        ("van den bruele stephanie haaltert 13 aug 1938.jpeg",
         "van den bruele stephanie haaltert 13 aug 1938 back.jpeg"),

    "Van Schandevijl Domien Denderhoutem bidprentje 27 februari 1941.jpeg":
        ("van schandevijl domien denderhoutem 27 feb 1941.jpeg",
         "van schandevijl domien denderhoutem 27 feb 1941_2.jpeg"),

    "Van Vaerenbergh Jan Baptist Denderhoutem bidprentje 30 september 1926.jpeg":
        ("vaerenbergh jan baptist denderhoutem sept 1926.jpeg",
         "vaerenbergh jan baptist denderhoutem sept 1926 (2).jpeg"),

    "Welleman Dionysius Kerksken  bidprentje 04 december 1860.jpeg":
        ("welleman dionysius kerksken 04 dec 1860.jpeg",
         "welleman dionysius kerksken 04 dec 1860_back.jpeg"),

    "Wynant Clementina Haaltert bidprentje 24 juli 1917.jpeg":
        ("wynant clementina haaltert juli 1917.jpeg",
         "wynant clementina haaltert juli 1917_verso.jpeg"),

    # === MODERATE ~30% — 7 pairs: swapped order, missing parts ===
    "Van den Bruelle Eduardus  Haaltert  bidprentje 26 november 1885.jpeg":
        ("Eduardus Van den Bruelle 1885.jpeg",
         "Eduardus Van den Bruelle 1885_b.jpeg"),

    "Van den Bruelle Jan  Haaltert  bidprentje 05 februari 1931.jpeg":
        ("Jan Vd Bruelle Haaltert 1931.jpeg",
         "Jan Vd Bruelle Haaltert 1931_back.jpeg"),

    "Van Schandevijl Rosalie Denderhoutem bidprentje 10 april 1937.jpeg":
        ("Rosalie Schandevijl 1937.jpeg",
         "Rosalie Schandevijl 1937 achterkant.jpeg"),

    "Van Schandevyl Alice Denderhoutem bidprentje 04 december 1941.jpeg":
        ("Alice Schandevyl Denderhoutem.jpeg",
         "Alice Schandevyl Denderhoutem_2.jpeg"),

    "Van Vaerenbergh Maria Josepha Denderhoutem bidprentje 26 november 1928.jpeg":
        ("Maria Josepha Vaerenbergh nov 1928.jpeg",
         "Maria Josepha Vaerenbergh nov 1928_back.jpeg"),

    "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg":
        ("Emiel Jozef Bruelle 18dec1928.jpeg",
         "Emiel Jozef Bruelle 18dec1928_achterkant.jpeg"),

    "Verbeken Romanie Kerksken   bidprentje 04 mei 1927.jpeg":
        ("Romanie Verbeken 1927.jpeg",
         "Romanie Verbeken 1927_b.jpeg"),

    # === HEAVY ~30% — 7 pairs: scanner-style, minimal info ===
    "Van Waeyenberghe Diogène  Haaltert bidprentje 17 augustus 1935.jpeg":
        ("scan_001_waeyenberghe.jpeg",
         "scan_002_waeyenberghe.jpeg"),

    "Van Wassenhove Delphine Kerksken bidprentje 09 oktober 1936.jpeg":
        ("IMG_20240301_wassenhove.jpeg",
         "IMG_20240301_wassenhove_back.jpeg"),

    "Verstraeten Stephanie Haaltert bidprentje 06 juni 1911.jpeg":
        ("bidprentje_verstraeten_1911.jpeg",
         "bidprentje_verstraeten_1911_2.jpeg"),

    "Volckaert Evelina Haaltert bidprentje 01 juli 1943.jpeg":
        ("scan_volckaert_evelina.jpeg",
         "scan_volckaert_evelina_verso.jpeg"),

    "Vonck Leo Pieter Haaltert bidprentje 10 augustus 1931.jpeg":
        ("IMG_vonck_leo.jpeg",
         "IMG_vonck_leo_back.jpeg"),

    "Vonck Yvonne Maria Haaltert bidprentje 02 januari 1946.jpeg":
        ("scan_055.jpeg",
         "scan_056.jpeg"),

    "Welleman Mathilde Kerksken  bidprentje 04 juni 1948.jpeg":
        ("foto_welleman_m.jpeg",
         "foto_welleman_m_achterkant.jpeg"),
}


def main():
    # Verify input_backup exists
    backup = INPUT_DIR.parent / "input_backup"
    if not backup.exists():
        print("ERROR: input_backup/ not found. Aborting.")
        return

    # Clear input and copy from backup fresh
    for f in INPUT_DIR.iterdir():
        if f.is_file():
            f.unlink()

    for f in backup.iterdir():
        if f.is_file():
            shutil.copy2(f, INPUT_DIR / f.name)

    print(f"Restored {len(list(INPUT_DIR.iterdir()))} files from backup")

    # Apply renames
    renamed = 0
    for orig_front, (new_front, new_back) in RENAMES.items():
        orig_back = orig_front.replace(".jpeg", " 1.jpeg")

        front_path = INPUT_DIR / orig_front
        back_path = INPUT_DIR / orig_back

        if front_path.exists():
            front_path.rename(INPUT_DIR / new_front)
            renamed += 1
        else:
            print(f"WARNING: front not found: {orig_front}")

        if back_path.exists():
            back_path.rename(INPUT_DIR / new_back)
            renamed += 1
        else:
            print(f"WARNING: back not found: {orig_back}")

    print(f"Renamed {renamed} files")
    print("Done! Input files are now fuzzy.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the rename script**

Run: `.venv/bin/python rename_inputs.py`
Expected: "Restored 46 files from backup" / "Renamed 46 files" / "Done!"

- [ ] **Step 3: Verify the input directory has messy names**

Run: `ls input/`
Expected: Mix of clean names, lowercase names, scanner-style names, etc.

- [ ] **Step 4: Update back-image detection regex to handle new suffixes**

The current regex in `src/images/pairing.py` only handles `1`, `back`, and `achterkant`. We need to also match `2`, `b`, `verso`, and parenthesized forms like `(2)`.

In `src/images/pairing.py`, update the `_BACK_SUFFIXES` regex. Changed from `[\s_]*` to `[\s_]+` to require at least one separator — prevents false positives on words ending in `b` (e.g., "bob.jpeg"):

```python
_BACK_SUFFIXES = re.compile(
    r"[\s_]+(\(2\)|1|2|back|achterkant|verso|b)\s*$", re.IGNORECASE
)
```

- [ ] **Step 5: Add tests for new back-image suffixes**

Add to `tests/test_pairing.py`:

```python
def test_is_back_image_with_suffix_2():
    assert is_back_image("card_2.jpeg") is True


def test_is_back_image_with_suffix_verso():
    assert is_back_image("card_verso.jpeg") is True


def test_is_back_image_with_suffix_b():
    assert is_back_image("card_b.jpeg") is True


def test_is_back_image_with_parenthesized_2():
    assert is_back_image("card (2).jpeg") is True


def test_normalize_removes_verso_suffix():
    assert normalize_filename("card_verso.jpeg") == "card"


def test_normalize_removes_parenthesized_2():
    assert normalize_filename("card (2).jpeg") == "card"
```

- [ ] **Step 6: Run all pairing tests**

Run: `.venv/bin/python -m pytest tests/test_pairing.py -v`
Expected: All PASS (including existing tests — make sure `_b` suffix doesn't break single-letter filenames. If `b` is too greedy, we can require `_b` or ` b` via the `[\s_]*` prefix which already requires a separator.)

- [ ] **Step 7: Remove the rename script and commit**

```bash
rm rename_inputs.py
git add input/ src/images/pairing.py tests/test_pairing.py
git commit -m "feat: rename input files to fuzzy variants, expand back-image detection"
```

---

### Task 8: Run Full Test Suite and Verify

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Manual end-to-end test**

Run: `.venv/bin/python -m src.main`

Verify the full pipeline:
1. **Match tab**: Scan shows fuzzy-named files being matched with varying confidence scores
2. **Extract tab**: After extraction, cards show derived filenames instead of raw stems
3. **Review tab**: Derived filename appears in header, updates live when editing fields
4. **Export button**: Shows count, clicking exports stitched images + `memorial_cards.json` to `output/`
5. **Output files**: Check `output/memorial_cards.json` has correct structure and `output/*.jpeg` files exist with canonical names

- [ ] **Step 3: Commit any fixes if needed**

Only if issues were found during manual testing.
