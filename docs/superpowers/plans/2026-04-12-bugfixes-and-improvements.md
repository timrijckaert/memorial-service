# Bugfixes and Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 reported issues: title-case names, saved-button feedback, age-at-death extraction/calculation, place name normalization, deceased-as-spouse guard, state persistence on restart, remove dead stitching code, untrack input folder from git.

**Architecture:** Mostly independent fixes across the LLM prompt, Python backend, and vanilla JS frontend. The persistence fix (Task 5) is the most involved, adding a `restore()` method to `MatchState` that reconstructs state from existing JSON files on disk. All other tasks are small, targeted changes.

**Tech Stack:** Python 3, vanilla JavaScript, JSON file storage, pytest

---

### Task 1: Title Case Names on Save

**Files:**
- Modify: `src/review/cards.py:30-35`
- Modify: `tests/test_review.py`
- Modify: `prompts/extract_person_system.txt:31`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_review.py`:

```python
def test_save_card_title_cases_names(tmp_path):
    original = {
        "person": {"first_name": "old", "last_name": "old"},
        "notes": [],
        "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"},
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {
        "person": {
            "first_name": "maria josepha",
            "last_name": "van den bruelle",
        },
        "notes": [],
        "source": {},
    }
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] == "Maria Josepha"
    assert result["person"]["last_name"] == "Van Den Bruelle"


def test_save_card_title_case_handles_none_names(tmp_path):
    original = {
        "person": {"first_name": None, "last_name": None},
        "notes": [],
        "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"},
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {
        "person": {"first_name": None, "last_name": None},
        "notes": [],
        "source": {},
    }
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] is None
    assert result["person"]["last_name"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_review.py::test_save_card_title_cases_names tests/test_review.py::test_save_card_title_case_handles_none_names -v`
Expected: FAIL — names stored as-is, not title-cased

- [ ] **Step 3: Implement title case in save_card**

Edit `src/review/cards.py` — replace the `save_card` function:

```python
def save_card(card_id: str, json_dir: Path, updated_data: dict) -> None:
    """Save corrected card data, preserving the original source field from disk."""
    json_path = json_dir / f"{card_id}.json"
    original = json.loads(json_path.read_text())
    # Title-case names before saving
    person = updated_data.get("person", {})
    if person:
        for field in ("first_name", "last_name"):
            value = person.get(field)
            if value:
                person[field] = value.title()
    merged = {**updated_data, "source": original["source"]}
    json_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_review.py -v`
Expected: ALL PASS

- [ ] **Step 5: Add title case instruction to LLM prompt**

Edit `prompts/extract_person_system.txt` — in the OUTPUT FIELDS section, change line 31 from:
```
- first_name: Given/first name(s) of the deceased
```
to:
```
- first_name: Given/first name(s) of the deceased (title case, e.g. "Maria Josepha")
```

And change line 32 from:
```
- last_name: Family/surname of the deceased
```
to:
```
- last_name: Family/surname of the deceased (title case, e.g. "Van Den Bruelle")
```

- [ ] **Step 6: Commit**

```bash
git add src/review/cards.py tests/test_review.py prompts/extract_person_system.txt
git commit -m "feat: title-case names on save and in LLM prompt"
```

---

### Task 2: Reset "Saved!" Button on Form Edit

**Files:**
- Modify: `src/web/static/app.js`

- [ ] **Step 1: Add markFormDirty function**

Add this function in `app.js` after the `computeDerivedName()` function (after line 702):

```javascript
function markFormDirty() {
  const btn = document.getElementById('approve-btn');
  if (btn.textContent === 'Saved!') {
    btn.textContent = 'Approve';
    btn.classList.remove('btn-success');
    btn.classList.add('btn-primary');
  }
}
```

- [ ] **Step 2: Wire markFormDirty to all review form fields**

In the `loadReviewCard()` function, after the line that sets `btn.classList.add('btn-primary');` (line 598), add:

```javascript
  // Reset dirty tracking on all form fields
  ['f-first_name', 'f-last_name', 'f-birth_date', 'f-birth_place',
   'f-death_date', 'f-death_place', 'f-age_at_death'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      computeDerivedName();
    };
  });
```

Also remove the existing inline `oninput="computeDerivedName()"` attributes from the HTML for these fields (in `index.html`) if present, since we now wire them programmatically. Check `index.html` for these.

- [ ] **Step 3: Wire markFormDirty to spouse inputs**

In the `addSpouseInput()` function, after `input.value = value;` (line 608), add:

```javascript
  input.oninput = markFormDirty;
```

- [ ] **Step 4: Manual test**

Start the app, go to review tab, click Approve (button turns green "Saved!"), edit any field. Verify button resets to blue "Approve". Click Approve again, verify it turns green "Saved!" again.

- [ ] **Step 5: Commit**

```bash
git add src/web/static/app.js src/web/static/index.html
git commit -m "fix: reset Saved! button to Approve when form fields change"
```

---

### Task 3: Age at Death — LLM Prompt + Review UI Auto-Calc

**Depends on:** Task 2 (uses `markFormDirty()` function added there)

**Files:**
- Modify: `prompts/extract_person_system.txt:28,37`
- Modify: `src/web/static/app.js`

- [ ] **Step 1: Rewrite age_at_death in LLM prompt**

Replace lines 28 and 37 in `prompts/extract_person_system.txt`. Change line 28 from:
```
- For age_at_death: ONLY populate this field when either birth_date or death_date is missing and you are using the age to deduce the missing date. If both birth_date and death_date are explicitly stated, set age_at_death to null — it is redundant.
```
to:
```
- AGE AT DEATH — STRICT RULES:
  - Extract age_at_death ONLY if the card explicitly states the age in the text (e.g. "in den ouderdom van 78 jaren", "oud 65 jaar").
  - DO NOT calculate age_at_death from birth_date and death_date. NEVER do arithmetic on dates to derive this field.
  - If the card does not explicitly mention the age, set age_at_death to null.
  - If both birth_date and death_date are explicitly stated on the card AND the age is also written, still extract the age as stated.
  - Example: card says "geboren 14 mei 1880, overleden 3 januari 1950" with no age mentioned → age_at_death: null
  - Example: card says "overleden in den ouderdom van 70 jaren" → age_at_death: 70
```

Change line 37 from:
```
- age_at_death: Age at death as an integer (ONLY when needed to deduce a missing date, otherwise null)
```
to:
```
- age_at_death: Age at death as integer, ONLY if explicitly stated on the card. null if not mentioned. NEVER calculate from dates.
```

- [ ] **Step 2: Add computeAge function to app.js**

Add after the `markFormDirty()` function:

```javascript
function computeAge() {
  var birthStr = document.getElementById('f-birth_date').value.trim();
  var deathStr = document.getElementById('f-death_date').value.trim();
  var ageField = document.getElementById('f-age_at_death');

  if (birthStr && deathStr && birthStr.match(/^\d{4}-\d{2}-\d{2}$/) && deathStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
    var birth = new Date(birthStr);
    var death = new Date(deathStr);
    var age = death.getFullYear() - birth.getFullYear();
    var monthDiff = death.getMonth() - birth.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && death.getDate() < birth.getDate())) {
      age--;
    }
    ageField.value = age;
    ageField.readOnly = true;
  } else {
    ageField.readOnly = false;
  }
  markFormDirty();
}
```

- [ ] **Step 3: Wire computeAge to date inputs**

In the `loadReviewCard()` function, update the oninput wiring added in Task 2. Replace the forEach block with:

```javascript
  ['f-first_name', 'f-last_name', 'f-birth_place', 'f-death_place'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      computeDerivedName();
    };
  });
  ['f-birth_date', 'f-death_date'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      computeAge();
      computeDerivedName();
    };
  });
  document.getElementById('f-age_at_death').oninput = markFormDirty;
```

Also call `computeAge()` at the end of `loadReviewCard()` to set the initial read-only state:

```javascript
  computeAge();
```

- [ ] **Step 4: Manual test**

Start the app, go to review tab. For a card with both birth and death dates: verify age is auto-calculated and field is read-only. Clear birth_date: verify age field becomes editable. Enter both dates again: verify age recalculates.

- [ ] **Step 5: Commit**

```bash
git add prompts/extract_person_system.txt src/web/static/app.js
git commit -m "feat: extract age only from card text, auto-calc in review UI"
```

---

### Task 4: Strengthen Place Name Normalization + Deceased-as-Spouse Guard

**Files:**
- Modify: `prompts/extract_person_system.txt`

- [ ] **Step 1: Add stronger place normalization instruction**

In `prompts/extract_person_system.txt`, before the `COMMON OCR MISSPELLINGS:` header (line 103), add:

```
MANDATORY CORRECTIONS:
You MUST apply every correction in the list below. If the OCR text contains any of the left-hand spellings, always replace with the right-hand spelling. Do not leave OCR-garbled place names uncorrected.

```

- [ ] **Step 2: Add deceased-as-spouse guard**

In `prompts/extract_person_system.txt`, after the existing spouse rules (after line 27 — the "Do NOT confuse a parent's name for a spouse" line), add:

```
  - The deceased's own name must NEVER appear in the spouses list. The spouses list contains ONLY the names of people the deceased was married to — never the deceased themselves.
```

- [ ] **Step 3: Commit**

```bash
git add prompts/extract_person_system.txt
git commit -m "fix: strengthen place normalization and add deceased-as-spouse guard in prompt"
```

---

### Task 5: Restore Match State on Restart

**Files:**
- Modify: `src/web/match_state.py`
- Modify: `src/web/server.py:240-254`
- Modify: `tests/test_match_state.py`

- [ ] **Step 1: Write the failing test for restore**

Add to `tests/test_match_state.py`:

```python
def test_restore_rebuilds_pairs_from_json(tmp_path):
    """restore() reconstructs confirmed pairs from existing skeleton JSONs."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    # Create fake input images
    _make_image(input_dir / "front.jpeg")
    _make_image(input_dir / "back.jpeg")

    # Create skeleton JSON as if a previous session had matched them
    card_id = str(uuid.uuid4())
    skeleton = {
        "source": {
            "front_image_file": "front.jpeg",
            "back_image_file": "back.jpeg",
        }
    }
    (json_dir / f"{card_id}.json").write_text(json.dumps(skeleton))

    state = MatchState(input_dir, output_dir, json_dir)
    state.restore()

    snapshot = state.get_snapshot()
    assert len(snapshot["pairs"]) == 1
    pair = snapshot["pairs"][0]
    assert pair["card_id"] == card_id
    assert pair["status"] == "auto_confirmed"
    assert pair["image_a"]["filename"] == "front.jpeg"
    assert pair["image_b"]["filename"] == "back.jpeg"


def test_restore_rebuilds_singles_from_json(tmp_path):
    """restore() reconstructs singles (back_image_file is null)."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    _make_image(input_dir / "single.jpeg")

    card_id = str(uuid.uuid4())
    skeleton = {
        "source": {
            "front_image_file": "single.jpeg",
            "back_image_file": None,
        }
    }
    (json_dir / f"{card_id}.json").write_text(json.dumps(skeleton))

    state = MatchState(input_dir, output_dir, json_dir)
    state.restore()

    snapshot = state.get_snapshot()
    assert len(snapshot["singles"]) == 1
    assert snapshot["singles"][0]["filename"] == "single.jpeg"
    assert snapshot["singles"][0]["card_id"] == card_id


def test_restore_skips_json_with_missing_source_images(tmp_path):
    """restore() ignores JSONs whose source images no longer exist in input/."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    # JSON references images that don't exist
    card_id = str(uuid.uuid4())
    skeleton = {
        "source": {
            "front_image_file": "gone.jpeg",
            "back_image_file": "also_gone.jpeg",
        }
    }
    (json_dir / f"{card_id}.json").write_text(json.dumps(skeleton))

    state = MatchState(input_dir, output_dir, json_dir)
    state.restore()

    snapshot = state.get_snapshot()
    assert len(snapshot["pairs"]) == 0
    assert len(snapshot["singles"]) == 0


def test_scan_skips_already_restored_images(tmp_path):
    """scan() does not re-pair images that are already part of restored pairs."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    # Create images
    _make_image(input_dir / "Person A 1920.jpeg")
    _make_image(input_dir / "Person A 1920 1.jpeg")
    _make_image(input_dir / "new_image.jpeg")

    # Restore a pair from a previous session
    card_id = str(uuid.uuid4())
    skeleton = {
        "source": {
            "front_image_file": "Person A 1920.jpeg",
            "back_image_file": "Person A 1920 1.jpeg",
        }
    }
    (json_dir / f"{card_id}.json").write_text(json.dumps(skeleton))

    state = MatchState(input_dir, output_dir, json_dir)
    state.restore()

    # Now scan — should only pick up new_image, not the already-restored pair
    result = state.scan()

    # The restored pair should still be there
    restored_ids = [p["card_id"] for p in result["pairs"] if p["card_id"] == card_id]
    assert len(restored_ids) == 1

    # new_image should be unmatched (no partner)
    unmatched_names = {u["filename"] for u in result["unmatched"]}
    assert "new_image.jpeg" in unmatched_names

    # The restored images should NOT appear in unmatched
    assert "Person A 1920.jpeg" not in unmatched_names
    assert "Person A 1920 1.jpeg" not in unmatched_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_match_state.py::test_restore_rebuilds_pairs_from_json tests/test_match_state.py::test_restore_rebuilds_singles_from_json tests/test_match_state.py::test_restore_skips_json_with_missing_source_images tests/test_match_state.py::test_scan_skips_already_restored_images -v`
Expected: FAIL — `MatchState` has no `restore()` method

- [ ] **Step 3: Implement restore() in MatchState**

Add this method to the `MatchState` class in `src/web/match_state.py`, after `__init__`:

```python
    def restore(self) -> None:
        """Reconstruct match state from existing JSON files on disk."""
        if not self._json_dir.exists():
            return

        with self._lock:
            restored_files = set()

            for json_path in sorted(self._json_dir.glob("*.json")):
                try:
                    data = json.loads(json_path.read_text())
                except (json.JSONDecodeError, OSError):
                    continue

                source = data.get("source", {})
                front_file = source.get("front_image_file")
                back_file = source.get("back_image_file")
                card_id = json_path.stem

                if not front_file:
                    continue

                # Skip if source images no longer exist
                if not (self._input_dir / front_file).exists():
                    continue
                if back_file and not (self._input_dir / back_file).exists():
                    continue

                if back_file:
                    self._pairs.append({
                        "image_a": {"filename": front_file},
                        "image_b": {"filename": back_file},
                        "score": 1.0,
                        "status": "auto_confirmed",
                        "card_id": card_id,
                    })
                    restored_files.add(front_file)
                    restored_files.add(back_file)
                else:
                    self._singles.append({
                        "filename": front_file,
                        "card_id": card_id,
                    })
                    restored_files.add(front_file)

            self._restored_files = restored_files
```

- [ ] **Step 4: Add _restored_files to __init__**

In `__init__`, add after `self._metadata`:

```python
        self._restored_files: set[str] = set()
```

- [ ] **Step 5: Update scan() to skip restored images**

In `src/web/match_state.py`, modify the `scan()` method. After the line `result = scan_and_match(self._input_dir)`, add filtering logic:

```python
        # Filter out images that were already restored from previous session
        if self._restored_files:
            result["pairs"] = [
                p for p in result["pairs"]
                if p["image_a"]["filename"] not in self._restored_files
                and p["image_b"]["filename"] not in self._restored_files
            ]
            result["unmatched"] = [
                u for u in result["unmatched"]
                if u["filename"] not in self._restored_files
            ]
```

Then inside the `with self._lock:` block, change the assignments from overwriting to extending. Replace:
```python
            self._pairs = result["pairs"]
            self._unmatched = result["unmatched"]
            self._singles = []
            self._metadata = {}
```
with:
```python
            new_pairs = result["pairs"]
            new_unmatched = result["unmatched"]
            # Keep restored pairs/singles, add newly scanned ones
            self._pairs = [p for p in self._pairs if p.get("card_id")] + new_pairs
            self._unmatched = new_unmatched
            # Don't clear singles — restored singles should persist
            self._metadata = {}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_match_state.py -v`
Expected: ALL PASS (both new and existing tests)

- [ ] **Step 7: Call restore() at server startup**

Edit `src/web/server.py` in the `make_server()` function. After the line `server.match_state = MatchState(input_dir, output_dir, json_dir)`, add:

```python
    server.match_state.restore()
```

- [ ] **Step 8: Commit**

```bash
git add src/web/match_state.py src/web/server.py tests/test_match_state.py
git commit -m "feat: restore match state from JSON files on startup"
```

---

### Task 6: Remove Redundant Match-Phase Stitching

**Files:**
- Modify: `src/web/match_state.py`
- Modify: `src/web/server.py:12`

- [ ] **Step 1: Remove stitch calls from confirm()**

In `src/web/match_state.py`, in the `confirm()` method, delete the stitching block (the lines after `card_id = matched_pair["card_id"]`):

```python
        # Stitch in background-safe way (outside lock)
        path_a = self._input_dir / filename_a
        path_b = self._input_dir / filename_b
        output_name = Path(filename_a).stem + ".jpeg"
        output_path = self._output_dir / output_name
        try:
            stitch_pair(path_a, path_b, output_path)
        except Exception:
            pass  # Stitching failure doesn't block confirmation
```

Keep only `return {"status": "confirmed", "card_id": card_id}`.

- [ ] **Step 2: Remove stitch calls from confirm_all()**

In `src/web/match_state.py`, in the `confirm_all()` method, delete the stitching loop:

```python
        for filename_a, filename_b in to_stitch:
            path_a = self._input_dir / filename_a
            path_b = self._input_dir / filename_b
            output_name = Path(filename_a).stem + ".jpeg"
            output_path = self._output_dir / output_name
            try:
                stitch_pair(path_a, path_b, output_path)
            except Exception:
                pass
```

Also remove the `to_stitch` list that collected filenames for stitching — specifically the line:
```python
        to_stitch = []
```
and inside the loop:
```python
                    to_stitch.append((
                        pair["image_a"]["filename"],
                        pair["image_b"]["filename"],
                    ))
```

- [ ] **Step 3: Remove stitch_pair import from match_state.py**

Remove the line:
```python
from src.images.stitching import stitch_pair
```

- [ ] **Step 4: Remove stitch_pair import from server.py**

Remove the line:
```python
from src.images.stitching import stitch_pair
```

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASS — stitching was never tested in match confirmation tests

- [ ] **Step 6: Commit**

```bash
git add src/web/match_state.py src/web/server.py
git commit -m "fix: remove redundant match-phase stitching (only export stitches)"
```

---

### Task 7: Untrack Input Folder from Git

**Files:**
- Git index only

- [ ] **Step 1: Verify files are tracked**

Run: `git ls-files input/ | head -5`
Expected: List of tracked image files

- [ ] **Step 2: Untrack without deleting**

Run: `git rm --cached -r input/`
Expected: `rm 'input/...'` for each file

- [ ] **Step 3: Verify untracked**

Run: `git ls-files input/`
Expected: Empty output

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: untrack input/ images (already in .gitignore)"
```

---

### Task 8: Merge to Main

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Merge feat/async-pipeline to main**

```bash
git checkout main
git merge feat/async-pipeline
```

- [ ] **Step 3: Verify merge**

Run: `git log --oneline -10`
Expected: All commits from feat/async-pipeline appear on main
