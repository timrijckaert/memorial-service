# Stable Card ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile filename-stem-based card identity with UUID4 assigned at match-confirm time, persisted as the JSON filename.

**Architecture:** UUID4 is minted in MatchState when a card is confirmed (user confirm, confirm-all, mark-single, or auto-confirm during scan). A skeleton JSON is written immediately to `output/json/<uuid>.json` containing only `source`. The worker enriches this file during extraction. All downstream consumers (review, server API, frontend deeplinks, export) use the UUID as the card identity. The derived name remains display-only.

**Tech Stack:** Python 3.12, stdlib `uuid`/`json`, vanilla JS frontend

---

### Task 1: MatchState — UUID Assignment (Keep Old Public API)

Add UUID minting and skeleton JSON creation to MatchState. Keep `get_confirmed_items()` and `get_snapshot()` returning old formats so existing consumers don't break.

**Files:**
- Modify: `src/web/match_state.py`
- Modify: `tests/test_match_state.py`

- [ ] **Step 1: Write new tests for UUID assignment**

Add these tests to `tests/test_match_state.py`:

```python
import json
import uuid


def test_confirm_creates_uuid_and_skeleton(tmp_path):
    """Confirming a pair assigns a UUID and writes a skeleton JSON."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Unmatch an auto-confirmed pair first, then confirm manually
    state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    # Re-pair manually so it's "suggested"
    state.manual_pair("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    result = state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "confirmed"
    assert "card_id" in result
    card_id = result["card_id"]
    # Valid UUID
    uuid.UUID(card_id)
    # Skeleton exists on disk
    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()
    skeleton = json.loads(skeleton_path.read_text())
    assert skeleton["source"]["front_image_file"] in ("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    assert skeleton["source"]["back_image_file"] in ("Person A 1920.jpeg", "Person A 1920 1.jpeg")


def test_confirm_all_creates_uuids(tmp_path):
    """confirm_all assigns UUIDs to all newly confirmed pairs."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Unmatch all auto-confirmed to get suggested pairs
    snapshot = state.get_snapshot()
    for pair in snapshot["pairs"]:
        state.unmatch(pair["image_a"]["filename"], pair["image_b"]["filename"])
    # Re-pair them
    state.manual_pair("Person A 1920.jpeg", "Person A 1920 1.jpeg")
    state.manual_pair("Person B 1950.jpeg", "Person B 1950 1.jpeg")

    state.confirm_all()

    snapshot = state.get_snapshot()
    confirmed = [p for p in snapshot["pairs"] if p["status"] == "confirmed"]
    assert len(confirmed) == 2
    for pair in confirmed:
        assert "card_id" in pair
        uuid.UUID(pair["card_id"])
        skeleton_path = json_dir / f"{pair['card_id']}.json"
        assert skeleton_path.exists()


def test_mark_single_creates_uuid_and_skeleton(tmp_path):
    """Marking as single assigns UUID and writes skeleton."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    result = state.mark_single("orphan.jpeg")

    assert result["status"] == "single"
    assert "card_id" in result
    card_id = result["card_id"]
    uuid.UUID(card_id)
    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()
    skeleton = json.loads(skeleton_path.read_text())
    assert skeleton["source"]["front_image_file"] == "orphan.jpeg"
    assert skeleton["source"]["back_image_file"] is None


def test_scan_auto_confirmed_creates_uuids(tmp_path):
    """Auto-confirmed pairs during scan get UUIDs and skeletons."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)

    result = state.scan()

    auto_confirmed = [p for p in result["pairs"] if p["status"] == "auto_confirmed"]
    assert len(auto_confirmed) >= 1
    for pair in auto_confirmed:
        assert "card_id" in pair
        uuid.UUID(pair["card_id"])
        skeleton_path = json_dir / f"{pair['card_id']}.json"
        assert skeleton_path.exists()


def test_unmatch_deletes_skeleton_json(tmp_path):
    """Unmatching a confirmed pair deletes its skeleton JSON."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    # Get a card_id from an auto-confirmed pair
    snapshot = state.get_snapshot()
    pair = [p for p in snapshot["pairs"] if p["status"] == "auto_confirmed"][0]
    card_id = pair["card_id"]
    skeleton_path = json_dir / f"{card_id}.json"
    assert skeleton_path.exists()

    state.unmatch(pair["image_a"]["filename"], pair["image_b"]["filename"])

    assert not skeleton_path.exists()


def test_confirm_auto_confirmed_keeps_existing_uuid(tmp_path):
    """Confirming an already auto-confirmed pair keeps the existing UUID."""
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    snapshot = state.get_snapshot()
    pair = [p for p in snapshot["pairs"] if p["status"] == "auto_confirmed"][0]
    original_card_id = pair["card_id"]

    result = state.confirm(pair["image_a"]["filename"], pair["image_b"]["filename"])

    assert result["card_id"] == original_card_id
    # Still only one skeleton file for this pair
    assert (json_dir / f"{original_card_id}.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_match_state.py -v`
Expected: FAIL — `MatchState.__init__() got unexpected keyword argument 'json_dir'` and missing `card_id` fields

- [ ] **Step 3: Implement UUID assignment in MatchState**

Update `src/web/match_state.py`:

1. Add imports: `import json`, `import uuid`
2. Add `json_dir` parameter to `__init__`: `def __init__(self, input_dir: Path, output_dir: Path, json_dir: Path | None = None)`
3. Store: `self._json_dir = json_dir or (output_dir / "json")`
4. Change `self._singles: list[str] = []` to `self._singles: list[dict] = []`
5. Add `_assign_card_id` method
6. Update `confirm()` — assign UUID if pair doesn't have one, write skeleton
7. Update `confirm_all()` — assign UUID for each newly confirmed pair
8. Update `mark_single()` — assign UUID, append dict to `_singles`
9. Update `scan()` — assign UUIDs to auto_confirmed pairs
10. Update `unmatch()` — delete skeleton JSON
11. Keep `get_confirmed_items()` returning old format (extract filename from _singles dict)
12. Keep `get_snapshot()` returning `"singles": [s["filename"] for s in self._singles]`

Key new method:

```python
def _assign_card_id(self, front_file: str, back_file: str | None) -> str:
    """Mint a UUID and write a skeleton JSON file."""
    card_id = str(uuid.uuid4())
    self._json_dir.mkdir(parents=True, exist_ok=True)
    skeleton = {
        "source": {
            "front_image_file": front_file,
            "back_image_file": back_file,
        }
    }
    (self._json_dir / f"{card_id}.json").write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False)
    )
    return card_id
```

Key changes to `confirm()`:

```python
def confirm(self, filename_a: str, filename_b: str) -> dict:
    card_id = None
    with self._lock:
        for pair in self._pairs:
            a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
            if {a, b} == {filename_a, filename_b}:
                pair["status"] = "confirmed"
                if "card_id" not in pair:
                    card_id = self._assign_card_id(a, b)
                    pair["card_id"] = card_id
                else:
                    card_id = pair["card_id"]
                break
        else:
            return {"status": "not_found"}

    # Stitch (outside lock) — same as before
    path_a = self._input_dir / filename_a
    path_b = self._input_dir / filename_b
    output_name = Path(filename_a).stem + ".jpeg"
    output_path = self._output_dir / output_name
    try:
        stitch_pair(path_a, path_b, output_path)
    except Exception:
        pass

    return {"status": "confirmed", "card_id": card_id}
```

Key changes to `unmatch()`:

```python
def unmatch(self, filename_a: str, filename_b: str) -> dict:
    card_id = None
    with self._lock:
        to_remove = None
        for i, pair in enumerate(self._pairs):
            a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
            if {a, b} == {filename_a, filename_b}:
                to_remove = i
                break

        if to_remove is None:
            return {"status": "not_found"}

        pair = self._pairs.pop(to_remove)
        card_id = pair.get("card_id")
        self._unmatched.append(pair["image_a"])
        self._unmatched.append(pair["image_b"])

    if card_id:
        json_path = self._json_dir / f"{card_id}.json"
        if json_path.exists():
            json_path.unlink()

    return {"status": "unmatched"}
```

Key changes to `mark_single()`:

```python
def mark_single(self, filename: str) -> dict:
    with self._lock:
        found = False
        new_unmatched = []
        for item in self._unmatched:
            if item["filename"] == filename:
                found = True
            else:
                new_unmatched.append(item)

        if not found:
            return {"status": "not_found"}

        self._unmatched = new_unmatched
        card_id = self._assign_card_id(filename, None)
        self._singles.append({"filename": filename, "card_id": card_id})

    return {"status": "single", "card_id": card_id}
```

Key changes to `confirm_all()`:

```python
def confirm_all(self) -> dict:
    to_stitch = []
    with self._lock:
        for pair in self._pairs:
            if pair["status"] == "suggested":
                pair["status"] = "confirmed"
                if "card_id" not in pair:
                    card_id = self._assign_card_id(
                        pair["image_a"]["filename"],
                        pair["image_b"]["filename"],
                    )
                    pair["card_id"] = card_id
                to_stitch.append((
                    pair["image_a"]["filename"],
                    pair["image_b"]["filename"],
                ))

    for filename_a, filename_b in to_stitch:
        path_a = self._input_dir / filename_a
        path_b = self._input_dir / filename_b
        output_name = Path(filename_a).stem + ".jpeg"
        output_path = self._output_dir / output_name
        try:
            stitch_pair(path_a, path_b, output_path)
        except Exception:
            pass

    return {"status": "confirmed", "count": len(to_stitch)}
```

Key changes to `scan()` — add after storing pairs:

```python
# Assign UUIDs to auto-confirmed pairs
for pair in self._pairs:
    if pair["status"] == "auto_confirmed" and "card_id" not in pair:
        card_id = self._assign_card_id(
            pair["image_a"]["filename"],
            pair["image_b"]["filename"],
        )
        pair["card_id"] = card_id
```

Keep `get_confirmed_items()` backwards-compatible:

```python
def get_confirmed_items(self) -> tuple[list[tuple[Path, Path]], list[Path]]:
    with self._lock:
        pairs = []
        for p in self._pairs:
            if p["status"] in ("confirmed", "auto_confirmed"):
                pairs.append((
                    self._input_dir / p["image_a"]["filename"],
                    self._input_dir / p["image_b"]["filename"],
                ))
        singles = [self._input_dir / s["filename"] for s in self._singles]
    return pairs, singles
```

Keep `get_snapshot()` backwards-compatible for singles:

```python
"singles": [s["filename"] for s in self._singles],
```

- [ ] **Step 4: Update existing test for mark_single**

The `test_mark_single` test checks `assert "orphan.jpeg" in snapshot["singles"]`. Since `get_snapshot()` still returns filenames as strings, this test still passes. No update needed.

- [ ] **Step 5: Run all tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_match_state.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/web/match_state.py tests/test_match_state.py
git commit -m "feat: assign UUID on match confirm, write skeleton JSON"
```

---

### Task 2: Interpretation — Skeleton Merge

Update `interpret_text` to read an existing JSON file (the skeleton from match phase) and merge extracted data into it, instead of writing a fresh file.

**Files:**
- Modify: `src/extraction/interpretation.py`
- Modify: `tests/test_interpret.py`

- [ ] **Step 1: Write test for skeleton merge**

Add to `tests/test_interpret.py`:

```python
def test_interpret_text_merges_into_existing_skeleton(tmp_path):
    """When output file already exists (skeleton), merge person/notes into it."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Some back text")
    output = tmp_path / "card.json"

    # Pre-create skeleton (simulating what match phase writes)
    skeleton = {
        "source": {
            "front_image_file": "scan_047.jpeg",
            "back_image_file": "scan_047_verso.jpeg",
        }
    }
    output.write_text(json.dumps(skeleton))

    interpret_text(
        front_text, back_text, output,
        SYSTEM_PROMPT, USER_TEMPLATE, backend,
        "scan_047.jpeg", "scan_047_verso.jpeg",
    )

    result = json.loads(output.read_text())
    # Person and notes from LLM response
    assert result["person"]["first_name"] == "Dominicus"
    assert len(result["notes"]) > 0
    # Source preserved from skeleton + text files added
    assert result["source"]["front_image_file"] == "scan_047.jpeg"
    assert result["source"]["back_image_file"] == "scan_047_verso.jpeg"
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card_back.txt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_interpret.py::test_interpret_text_merges_into_existing_skeleton -v`
Expected: FAIL — skeleton's image files are overwritten with parameters (currently the source is built fresh)

- [ ] **Step 3: Implement skeleton merge**

Update `src/extraction/interpretation.py`:

Replace the end of `interpret_text` (after LLM call and JSON parsing) with:

```python
    # Read existing file (skeleton from match phase) if present
    existing = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text())

    # Merge extracted data into existing structure
    existing["person"] = result.get("person", {})
    existing["notes"] = result.get("notes", [])
    existing_source = existing.get("source", {})
    existing_source["front_text_file"] = front_text_path.name
    existing_source["back_text_file"] = back_text_path.name
    if front_image_file is not None:
        existing_source["front_image_file"] = front_image_file
    if back_image_file is not None:
        existing_source["back_image_file"] = back_image_file
    existing["source"] = existing_source

    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
```

This replaces the old lines:
```python
    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
        "front_image_file": front_image_file,
        "back_image_file": back_image_file,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run all interpretation tests**

Run: `.venv/bin/python -m pytest tests/test_interpret.py -v`
Expected: ALL PASS (existing tests work because output_path doesn't pre-exist, so `existing = {}`)

- [ ] **Step 5: Commit**

```bash
git add src/extraction/interpretation.py tests/test_interpret.py
git commit -m "feat: interpret_text merges into existing skeleton JSON"
```

---

### Task 3: UUID Propagation — get_confirmed_items + Worker + Server

Change `get_confirmed_items()` to return card_id tuples, update the worker to accept them, and update the server to wire everything through with UUIDs. This is a coordinated change — all three must update together for tests to pass.

**Files:**
- Modify: `src/web/match_state.py:180-192` (get_confirmed_items + get_snapshot)
- Modify: `src/web/worker.py`
- Modify: `src/web/server.py`
- Modify: `tests/test_match_state.py`
- Modify: `tests/test_worker.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Update get_confirmed_items return type**

In `src/web/match_state.py`, replace `get_confirmed_items`:

```python
def get_confirmed_items(self) -> tuple[list[tuple[str, Path, Path]], list[tuple[str, Path]]]:
    """Return confirmed pairs and singles with card_ids for the extract pipeline."""
    with self._lock:
        pairs = []
        for p in self._pairs:
            if p["status"] in ("confirmed", "auto_confirmed"):
                pairs.append((
                    p["card_id"],
                    self._input_dir / p["image_a"]["filename"],
                    self._input_dir / p["image_b"]["filename"],
                ))
        singles = [
            (s["card_id"], self._input_dir / s["filename"])
            for s in self._singles
        ]

    return pairs, singles
```

Also update `get_snapshot()` to return dict-based singles:

```python
"singles": [dict(s) for s in self._singles],
```

- [ ] **Step 2: Update match_state test for new return types**

In `tests/test_match_state.py`, replace `test_get_confirmed_pairs_for_extract`:

```python
def test_get_confirmed_pairs_for_extract(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()
    state.mark_single("orphan.jpeg")

    pairs, singles = state.get_confirmed_items()

    assert len(pairs) == 2
    assert len(singles) == 1
    # Each pair is (card_id, front_path, back_path)
    card_id, front, back = pairs[0]
    uuid.UUID(card_id)  # valid UUID
    assert front.name.endswith(".jpeg")
    # Single is (card_id, path)
    single_id, single_path = singles[0]
    uuid.UUID(single_id)
    assert single_path.name == "orphan.jpeg"
```

Update `test_mark_single` to handle dict-based singles in snapshot:

```python
def test_mark_single(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    state = MatchState(tmp_path, output_dir, json_dir)
    state.scan()

    result = state.mark_single("orphan.jpeg")

    assert result["status"] == "single"
    snapshot = state.get_snapshot()
    assert any(s["filename"] == "orphan.jpeg" for s in snapshot["singles"])
    unmatched_names = {u["filename"] for u in snapshot["unmatched"]}
    assert "orphan.jpeg" not in unmatched_names
```

- [ ] **Step 3: Update worker to accept UUID-based tuples**

In `src/web/worker.py`:

Change `start()` signature and queue_names:

```python
def start(
    self,
    pairs: list[tuple[str, Path, Path | None]],
    text_dir: Path,
    ...
) -> bool:
    with self._lock:
        if self._status.status == "running":
            return False
        queue_names = [card_id for card_id, _, _ in pairs]
        self._status = ExtractionStatus(
            status="running", queue=queue_names,
        )
    ...
```

Change `_ocr_producer` to unpack (card_id, front, back):

```python
async def _ocr_producer(self, pairs, text_dir, ocr_queue, executor):
    loop = asyncio.get_running_loop()

    async def ocr_one(card_id: str, front_path: Path, back_path: Path | None):
        card_name = card_id
        ...
        front_text_path = text_dir / f"{card_id}_front.txt"
        back_text_path = text_dir / f"{card_id}_back.txt" if back_path else None
        ...

    await asyncio.gather(*(ocr_one(cid, f, b) for cid, f, b in pairs))
    await ocr_queue.put(None)
```

The `_llm_consumer` needs no changes — it already uses `item.card_name` from `_OcrResult`, and `json_output_path = json_dir / f"{card_name}.json"` correctly points to the UUID-named file.

- [ ] **Step 4: Update worker tests**

In `tests/test_worker.py`, change all pair tuples from `(Path, Path)` to `(card_id, Path, Path)`:

```python
@patch("src.web.worker.interpret_text")
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.extract_text")
def test_worker_processes_card(mock_ocr, mock_verify, mock_interpret, tmp_path):
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    worker = ExtractionWorker()
    card_id = "test-uuid-001"
    started = worker.start(
        [(card_id, front, back)], text_dir, json_dir, tmp_path,
        "system", "template", MagicMock(),
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert card_id in status.done
    assert mock_ocr.call_count == 2
    assert mock_verify.call_count == 2
    assert mock_interpret.call_count == 1
```

Apply the same pattern to all worker tests:
- `test_worker_reports_ocr_errors`: use `("err-uuid", front, back)`, assert `status.errors[0].card_id == "err-uuid"`
- `test_worker_skips_llm_without_backend`: use `("no-llm-uuid", front, back)`, assert `"no-llm-uuid" in status.done`
- `test_worker_rejects_double_start`: use `("dbl-uuid", front, back)`
- `test_worker_cancellation`: use `(f"cancel-uuid-{i}", front, back)` for each pair
- `test_worker_processes_multiple_cards`: use `(f"multi-uuid-{name}", front, back)`, assert `sorted(status.done) == sorted(["multi-uuid-Card A", "multi-uuid-Card B", "multi-uuid-Card C"])`

- [ ] **Step 5: Update server.py — make_server and extract endpoints**

In `src/web/server.py`:

Update `make_server` to pass `json_dir`:

```python
server.match_state = MatchState(input_dir, output_dir, json_dir)
```

Update extract/cards endpoint (`do_GET`, the `/api/extract/cards` branch):

```python
elif self.path == "/api/extract/cards":
    pairs, singles = self.server.match_state.get_confirmed_items()
    cards = []
    for card_id, front, back in pairs:
        json_path = json_dir / f"{card_id}.json"
        card_data = json.loads(json_path.read_text()) if json_path.exists() else {}
        has_person = "person" in card_data
        derived_name = derive_filename(card_data) if has_person else None
        cards.append({
            "card_id": card_id,
            "front": front.name,
            "back": back.name,
            "status": "done" if has_person else "pending",
            "derived_name": derived_name,
        })
    for card_id, single in singles:
        json_path = json_dir / f"{card_id}.json"
        card_data = json.loads(json_path.read_text()) if json_path.exists() else {}
        has_person = "person" in card_data
        derived_name = derive_filename(card_data) if has_person else None
        cards.append({
            "card_id": card_id,
            "front": single.name,
            "back": None,
            "status": "done" if has_person else "pending",
            "derived_name": derived_name,
        })
    self._send_json({"cards": cards})
```

Update extract POST (`do_POST`, the `/api/extract` branch):

```python
pairs, singles = self.server.match_state.get_confirmed_items()
all_items = [(cid, f, b) for cid, f, b in pairs] + [(cid, f, None) for cid, f in singles]
if cards_filter:
    card_set = set(cards_filter)
    all_items = [(cid, f, b) for cid, f, b in all_items if cid in card_set]
```

Update export count to only count fully-extracted cards:

```python
elif self.path == "/api/export/count":
    count = sum(
        1 for p in json_dir.glob("*.json")
        if "person" in json.loads(p.read_text())
    )
    self._send_json({"count": count})
```

- [ ] **Step 6: Update server tests**

Key test updates in `tests/test_server.py`:

Update `test_api_extract_cards_lists_eligible` — check `card_id` instead of `name`:

```python
def test_api_extract_cards_lists_eligible(tmp_path):
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
        resp = urlopen(f"{base}/api/extract/cards")
        data = json.loads(resp.read())
        assert len(data["cards"]) == 1
        assert "card_id" in data["cards"][0]
        assert data["cards"][0]["status"] == "pending"
    finally:
        server.shutdown()
```

Update `test_api_extract_skips_already_extracted` — enrich skeleton instead of pre-creating stem-named file:

```python
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
```

Update `test_api_export_count_returns_json_count` — only fully-extracted cards count:

```python
def test_api_export_count_returns_json_count(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    (json_dir / "card1.json").write_text('{"person": {"first_name": "A"}, "notes": [], "source": {}}')
    (json_dir / "card2.json").write_text('{"person": {"first_name": "B"}, "notes": [], "source": {}}')
    # Skeleton only — should NOT count
    (json_dir / "skeleton.json").write_text('{"source": {"front_image_file": "x.jpeg"}}')

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/export/count")
        data = json.loads(resp.read())
        assert data["count"] == 2
    finally:
        server.shutdown()
```

Update `test_api_match_scan_returns_pairs` — pairs now include `card_id`:

```python
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
```

The `test_api_extract_starts_and_completes` test needs the worker to receive UUID tuples. Since scan() auto-confirms and assigns UUIDs, and the server now passes `(card_id, front, back)` to the worker, this test should work without changes (the worker receives UUID-based tuples from the server). But verify the done list check:

```python
assert len(status["done"]) == 1
```

This checks count, not specific names, so it still works.

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_match_state.py tests/test_worker.py tests/test_server.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/web/match_state.py src/web/worker.py src/web/server.py tests/test_match_state.py tests/test_worker.py tests/test_server.py
git commit -m "feat: propagate UUID through worker and server APIs"
```

---

### Task 4: Frontend — UUID-Based Navigation

Update `app.js` to use `card_id` (UUID) for deeplinks, API calls, and checkbox values. Display `derived_name` for user-facing text.

**Files:**
- Modify: `src/web/static/app.js`

- [ ] **Step 1: Update extract list to use card_id**

In the `renderExtractList` function, change the card identity from `c.name` to `c.card_id`:

```javascript
const cardId = c.card_id || '';
const displayName = c.derived_name || cardId;
```

- [ ] **Step 2: Update polling merge to use card_id**

In `pollExtractStatus`, the `workerMap` lookup and merge use `c.name`. Change to `c.card_id`:

```javascript
var merged = allCards.map(function(c) {
    var w = workerMap[c.card_id];
    if (w) return { card_id: c.card_id, derived_name: c.derived_name, icon: w.icon, statusText: w.statusText, status: w.icon };
    return { card_id: c.card_id, derived_name: c.derived_name, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : c.status, status: c.status };
});
```

- [ ] **Step 3: Update match UI for dict-based singles**

In `renderMatchUI`, the singles iteration now receives objects instead of strings:

```javascript
matchData.singles.forEach(function(single) {
    var card = document.createElement('div');
    card.className = 'match-unmatched-card';
    card.style.borderColor = '#888';
    card.innerHTML =
        '<img src="/images/' + encodeURIComponent(single.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(single.filename)) + '>' +
        '<div class="filename">' + single.filename + '</div>' +
        '<div class="details" style="color:#888;">Marked as single</div>';
    sGrid.appendChild(card);
});
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/static/app.js
git commit -m "feat: frontend uses UUID for deeplinks and card identity"
```

---

### Task 5: Export — Skip Skeleton-Only JSONs

The export phase now encounters skeleton JSONs (source-only, no person data). It must skip these.

**Files:**
- Modify: `src/export.py`
- Modify: `tests/test_export.py`

- [ ] **Step 1: Write test for skeleton-only JSON being skipped**

Add to `tests/test_export.py`:

```python
def test_export_skips_skeleton_only_json(tmp_path):
    """Skeleton JSONs (no person data) are skipped during export."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    # Skeleton-only (from match phase, not yet extracted)
    skeleton = {"source": {"front_image_file": "scan.jpeg", "back_image_file": None}}
    (json_dir / "skeleton-uuid.json").write_text(json.dumps(skeleton))

    # Fully extracted card
    _make_image(input_dir / "front.jpeg")
    _make_card_json(
        json_dir, "extracted-uuid",
        person={"first_name": "Jan", "last_name": "Pieters", "birth_place": None,
                "death_date": "1950-06-01", "death_place": None, "birth_date": None,
                "age_at_death": None, "spouses": []},
        front_image="front.jpeg",
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_export.py::test_export_skips_skeleton_only_json -v`
Expected: FAIL — exported 2 instead of 1

- [ ] **Step 3: Add skeleton skip in run_export**

In `src/export.py`, add a skip check at the top of the card loop:

```python
for card_path in card_files:
    data = json.loads(card_path.read_text())
    if "person" not in data:
        continue  # Skip skeleton-only files

    source = data.get("source", {})
    ...
```

- [ ] **Step 4: Run all export tests**

Run: `.venv/bin/python -m pytest tests/test_export.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat: export skips skeleton-only JSON files"
```

---

### Task 6: Full Test Suite Verification

Run the entire test suite to ensure everything works together.

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASS (should be 131+ tests)

- [ ] **Step 2: Manually verify key flows**

Check these integration points:
- Skeleton JSONs exist in `output/json/` with UUID filenames after match
- Card data is correctly identified by UUID in API responses
- Export only processes fully-extracted cards

Run: `.venv/bin/python -m pytest tests/ -v --tb=short`

If any test fails, fix it.

- [ ] **Step 3: Commit any fixes if needed**
