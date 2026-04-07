# Async Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallelize OCR across cards (and front/back within a card) while keeping LLM calls sequential, using an asyncio two-stage producer-consumer pipeline.

**Architecture:** The worker spawns an asyncio event loop on a daemon thread. An OCR producer launches all cards' OCR concurrently via `run_in_executor` (front+back in parallel per card). Completed OCR results flow through an `asyncio.Queue` to a single LLM consumer that processes date verification and interpretation one card at a time (also via `run_in_executor`). The existing sync HTTP server and extraction modules are unchanged.

**Tech Stack:** Python asyncio, concurrent.futures.ThreadPoolExecutor, asyncio.Queue

**Deviation from spec:** The spec called for `AsyncLLMBackend`, `AsyncOllamaBackend`, and `httpx`. Instead, we use `run_in_executor` to call the existing sync `verify_dates`/`interpret_text` functions from the async event loop. This avoids changing the extraction modules, eliminates a new dependency, and achieves identical performance since the LLM consumer is sequential anyway.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/web/worker.py` | Rewrite | Async two-stage pipeline, new status model with `in_flight` |
| `src/web/static/index.html` | Modify | Replace single-card pipeline view with in-flight list container |
| `src/web/static/app.js` | Modify | Render multiple in-flight cards, update polling for new status shape |
| `tests/test_worker.py` | Rewrite | Tests for async worker behavior |
| `tests/test_server.py` | Modify | Update patches from `extract_one` to individual functions |

**Not modified:** `src/extraction/pipeline.py`, `src/extraction/llm.py`, `src/extraction/ocr.py`, `src/extraction/date_verification.py`, `src/extraction/interpretation.py`, `src/web/server.py`, `src/extraction/__init__.py`

---

### Task 1: Update status model and serialization

**Files:**
- Modify: `src/web/worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Write failing test for new status shape**

```python
# tests/test_worker.py — replace test_extraction_status_to_dict

def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict with in_flight."""
    from src.web.worker import ExtractionStatus, CardError, CardProgress

    status = ExtractionStatus(
        status="running",
        in_flight=[CardProgress("card1", "ocr"), CardProgress("card2", "date_verify")],
        done=["card0"],
        errors=[CardError("card3", "failed")],
        queue=["card4"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["in_flight"] == [
        {"card_id": "card1", "stage": "ocr"},
        {"card_id": "card2", "stage": "date_verify"},
    ]
    assert d["done"] == ["card0"]
    assert d["errors"] == [{"card_id": "card3", "reason": "failed"}]
    assert d["queue"] == ["card4"]
    assert "current" not in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_worker.py::test_extraction_status_to_dict -v`
Expected: FAIL — `CardProgress` does not exist yet

- [ ] **Step 3: Implement CardProgress and update ExtractionStatus**

Replace the status model in `src/web/worker.py`:

```python
@dataclass
class CardProgress:
    """Tracks a single in-flight card and its current stage."""
    card_id: str
    stage: str  # "ocr" | "date_verify" | "llm_extract"


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    in_flight: list[CardProgress] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)
```

Remove the old `current: dict | None = None` field.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_worker.py::test_extraction_status_to_dict -v`
Expected: PASS

- [ ] **Step 5: Write test for idle status defaults**

```python
# tests/test_worker.py — replace test_worker_starts_idle

def test_worker_starts_idle():
    """New worker starts in idle status with empty in_flight."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.in_flight == []
    assert status.done == []
    assert status.errors == []
    assert status.queue == []
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_worker.py::test_worker_starts_idle -v`
Expected: FAIL for now — `ExtractionWorker.__init__` and `get_status` are updated in Task 2 when the full worker is rewritten. Continue to Task 2 without committing.

**Note:** Tasks 1 and 2 are committed together after the full worker rewrite. The status model tests validate the target shape; the worker implementation in Task 2 makes them pass.

---

### Task 2: Rewrite ExtractionWorker to async pipeline

**Files:**
- Modify: `src/web/worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Write test for single card processing**

```python
# tests/test_worker.py

@patch("src.web.worker.interpret_text")
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.extract_text")
def test_worker_processes_card(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Worker processes a card through OCR and LLM stages."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    worker = ExtractionWorker()
    started = worker.start(
        [(front, back)], text_dir, json_dir, tmp_path,
        "system", "template", MagicMock(),
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done
    assert mock_ocr.call_count == 2  # front + back
    assert mock_verify.call_count == 2  # front + back
    assert mock_interpret.call_count == 1
```

- [ ] **Step 2: Write test for OCR error handling**

```python
@patch("src.web.worker.extract_text", side_effect=RuntimeError("tesseract crashed"))
def test_worker_reports_ocr_errors(mock_ocr, tmp_path):
    """Cards with OCR failures go to errors, not the LLM queue."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], text_dir, tmp_path, tmp_path,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "Card"
    assert status.done == []
```

- [ ] **Step 3: Write test for no-backend mode (OCR only)**

```python
@patch("src.web.worker.extract_text")
def test_worker_skips_llm_without_backend(mock_ocr, tmp_path):
    """Without a backend, only OCR runs and cards go to done."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], text_dir, tmp_path, tmp_path,
        None, None, None,  # no backend
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done
    assert mock_ocr.call_count == 2
```

- [ ] **Step 4: Write test for double-start rejection**

```python
def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()

    def slow_ocr(*args, **kwargs):
        time.sleep(1)

    with patch("src.web.worker.extract_text", side_effect=slow_ocr):
        worker = ExtractionWorker()
        worker.start(
            [(front, back)], text_dir, tmp_path, tmp_path,
            None, None, None,
        )
        second = worker.start(
            [(front, back)], text_dir, tmp_path, tmp_path,
            None, None, None,
        )

    assert second is False
```

- [ ] **Step 5: Write test for cancellation**

```python
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.interpret_text")
def test_worker_cancellation(mock_interpret, mock_verify, tmp_path):
    """Cancelling stops processing after the current card."""
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = tmp_path / f"{name}.jpeg"
        back = tmp_path / f"{name} 1.jpeg"
        front.touch()
        back.touch()
        pairs.append((front, back))

    def slow_ocr(*args, **kwargs):
        time.sleep(0.5)

    with patch("src.web.worker.extract_text", side_effect=slow_ocr):
        worker = ExtractionWorker()
        worker.start(
            pairs, text_dir, tmp_path, tmp_path,
            "sys", "tmpl", MagicMock(),
        )
        time.sleep(0.3)
        worker.cancel()

        for _ in range(50):
            time.sleep(0.1)
            status = worker.get_status()
            if status.status in ("idle", "cancelled"):
                break

    assert status.status in ("idle", "cancelled")
    total_processed = len(status.done) + len(status.errors)
    assert total_processed < 3  # not all cards processed
```

- [ ] **Step 6: Write test for multiple cards completing**

```python
@patch("src.web.worker.interpret_text")
@patch("src.web.worker.verify_dates", return_value=[])
@patch("src.web.worker.extract_text")
def test_worker_processes_multiple_cards(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """All cards in a batch are processed."""
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = tmp_path / f"{name}.jpeg"
        back = tmp_path / f"{name} 1.jpeg"
        front.touch()
        back.touch()
        pairs.append((front, back))

    worker = ExtractionWorker()
    worker.start(
        pairs, text_dir, json_dir, tmp_path,
        "sys", "tmpl", MagicMock(),
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert sorted(status.done) == ["Card A", "Card B", "Card C"]
    assert mock_ocr.call_count == 6  # 2 per card
    assert mock_interpret.call_count == 3
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`
Expected: FAIL — worker still uses old `extract_one` import

- [ ] **Step 8: Implement the async ExtractionWorker**

Replace the full `src/web/worker.py` with:

```python
# src/web/worker.py
"""Background extraction worker using async two-stage pipeline."""

import asyncio
import dataclasses
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.extraction.ocr import extract_text
from src.extraction.date_verification import verify_dates
from src.extraction.interpretation import interpret_text
from src.extraction.llm import LLMBackend


@dataclass
class CardError:
    """An error that occurred during extraction of a single card."""
    card_id: str
    reason: str


@dataclass
class CardProgress:
    """Tracks a single in-flight card and its current stage."""
    card_id: str
    stage: str  # "ocr" | "date_verify" | "llm_extract"


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    in_flight: list[CardProgress] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class _OcrResult:
    """Internal data passed from OCR stage to LLM stage."""
    card_name: str
    front_path: Path
    back_path: Path
    front_text_path: Path
    back_text_path: Path


class ExtractionWorker:
    """Runs extraction via async two-stage pipeline on a background thread.

    Stage 1 (OCR producer): launches all cards' OCR concurrently via
    ThreadPoolExecutor. Front + back OCR run in parallel per card.

    Stage 2 (LLM consumer): pulls OCR-completed cards from an asyncio.Queue
    and runs date verification + interpretation one card at a time.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status = ExtractionStatus(status="idle")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cancel: asyncio.Event | None = None

    def get_status(self) -> ExtractionStatus:
        with self._lock:
            return ExtractionStatus(
                status=self._status.status,
                in_flight=[
                    CardProgress(p.card_id, p.stage)
                    for p in self._status.in_flight
                ],
                done=list(self._status.done),
                errors=[
                    CardError(e.card_id, e.reason)
                    for e in self._status.errors
                ],
                queue=list(self._status.queue),
            )

    def start(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ) -> bool:
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._status = ExtractionStatus(
                status="running", queue=queue_names,
            )

        thread = threading.Thread(
            target=self._run_loop,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"
        if self._loop and self._cancel:
            self._loop.call_soon_threadsafe(self._cancel.set)

    def _run_loop(self, pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend):
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._cancel = asyncio.Event()
        try:
            loop.run_until_complete(
                self._run(pairs, text_dir, json_dir, conflicts_dir,
                          system_prompt, user_template, backend)
            )
        finally:
            loop.close()
            self._loop = None
            self._cancel = None

    async def _run(self, pairs, text_dir, json_dir, conflicts_dir,
                   system_prompt, user_template, backend):
        ocr_queue: asyncio.Queue[_OcrResult | None] = asyncio.Queue()
        executor = ThreadPoolExecutor(max_workers=4)

        try:
            producer = asyncio.create_task(
                self._ocr_producer(pairs, text_dir, ocr_queue, executor)
            )
            consumer = asyncio.create_task(
                self._llm_consumer(
                    ocr_queue, executor, json_dir, conflicts_dir,
                    system_prompt, user_template, backend,
                )
            )
            await asyncio.gather(producer, consumer)
        finally:
            executor.shutdown(wait=False)

        with self._lock:
            if self._status.status != "cancelled":
                self._status.status = "idle"

    async def _ocr_producer(self, pairs, text_dir, ocr_queue, executor):
        loop = asyncio.get_event_loop()

        async def ocr_one(front_path: Path, back_path: Path):
            card_name = front_path.stem
            if self._cancel.is_set():
                return

            with self._lock:
                if card_name in self._status.queue:
                    self._status.queue.remove(card_name)
                self._status.in_flight.append(
                    CardProgress(card_name, "ocr")
                )

            front_text_path = text_dir / f"{front_path.stem}_front.txt"
            back_text_path = text_dir / f"{back_path.stem}_back.txt"

            try:
                await asyncio.gather(
                    loop.run_in_executor(
                        executor, extract_text,
                        front_path, front_text_path,
                    ),
                    loop.run_in_executor(
                        executor, extract_text,
                        back_path, back_text_path,
                    ),
                )
            except Exception as e:
                with self._lock:
                    self._status.in_flight = [
                        p for p in self._status.in_flight
                        if p.card_id != card_name
                    ]
                    self._status.errors.append(
                        CardError(card_name, f"OCR: {e}")
                    )
                return

            with self._lock:
                self._status.in_flight = [
                    p for p in self._status.in_flight
                    if p.card_id != card_name
                ]

            await ocr_queue.put(_OcrResult(
                card_name=card_name,
                front_path=front_path,
                back_path=back_path,
                front_text_path=front_text_path,
                back_text_path=back_text_path,
            ))

        await asyncio.gather(*(ocr_one(f, b) for f, b in pairs))
        await ocr_queue.put(None)  # sentinel

    async def _llm_consumer(self, ocr_queue, executor, json_dir,
                            conflicts_dir, system_prompt, user_template,
                            backend):
        loop = asyncio.get_event_loop()

        while True:
            item = await ocr_queue.get()
            if item is None:
                break

            if self._cancel.is_set():
                continue  # drain remaining items

            if not backend:
                with self._lock:
                    self._status.done.append(item.card_name)
                continue

            card_name = item.card_name

            # Date verification
            with self._lock:
                self._status.in_flight.append(
                    CardProgress(card_name, "date_verify")
                )

            try:
                for txt_path, img_path in [
                    (item.front_text_path, item.front_path),
                    (item.back_text_path, item.back_path),
                ]:
                    await loop.run_in_executor(
                        executor, verify_dates,
                        img_path, txt_path, backend, conflicts_dir,
                    )
            except Exception as e:
                with self._lock:
                    self._status.in_flight = [
                        p for p in self._status.in_flight
                        if p.card_id != card_name
                    ]
                    self._status.errors.append(
                        CardError(card_name, f"date verify: {e}")
                    )
                continue

            # LLM interpretation
            with self._lock:
                for p in self._status.in_flight:
                    if p.card_id == card_name:
                        p.stage = "llm_extract"
                        break

            json_output_path = json_dir / f"{card_name}.json"
            try:
                await loop.run_in_executor(
                    executor, interpret_text,
                    item.front_text_path, item.back_text_path,
                    json_output_path,
                    system_prompt, user_template, backend,
                )
            except Exception as e:
                with self._lock:
                    self._status.in_flight = [
                        p for p in self._status.in_flight
                        if p.card_id != card_name
                    ]
                    self._status.errors.append(
                        CardError(card_name, f"interpret: {e}")
                    )
                continue

            with self._lock:
                self._status.in_flight = [
                    p for p in self._status.in_flight
                    if p.card_id != card_name
                ]
                self._status.done.append(card_name)
```

- [ ] **Step 9: Run worker tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add src/web/worker.py tests/test_worker.py
git commit -m "feat: rewrite worker to async two-stage pipeline"
```

---

### Task 3: Update server tests for new worker

**Files:**
- Modify: `tests/test_server.py`

The server code (`src/web/server.py`) does not need changes — it just calls `worker.get_status().to_dict()` which now returns the new shape. But the server tests mock `src.web.worker.extract_one`, which the worker no longer imports.

- [ ] **Step 1: Update test_api_extract_starts_and_completes**

Replace the mock from `extract_one` to individual functions:

```python
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
    _create_test_image(output_dir / "Card A.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with patch("src.web.worker.extract_text"), \
             patch("src.web.worker.verify_dates", return_value=[]), \
             patch("src.web.worker.interpret_text"):

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
```

- [ ] **Step 2: Update test_api_extract_cancel_stops_worker**

Replace the mock:

```python
def test_api_extract_cancel_stops_worker(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    text_dir = output_dir / "text"
    text_dir.mkdir()

    for name in ["Card A", "Card B", "Card C"]:
        _create_test_image(input_dir / f"{name}.jpeg", color="red")
        _create_test_image(input_dir / f"{name} 1.jpeg", color="blue")
        _create_test_image(output_dir / f"{name}.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        def slow_ocr(*args, **kwargs):
            time.sleep(0.5)

        with patch("src.web.worker.extract_text", side_effect=slow_ocr), \
             patch("src.web.worker.verify_dates", return_value=[]), \
             patch("src.web.worker.interpret_text"):

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
```

- [ ] **Step 3: Remove unused import**

Remove the `ExtractionResult` import from `tests/test_server.py` (line 12) since it's no longer needed.

- [ ] **Step 4: Run server tests**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_server.py
git commit -m "test: update server tests for async worker"
```

---

### Task 4: Update extract UI for in-flight cards

**Files:**
- Modify: `src/web/static/index.html`
- Modify: `src/web/static/app.js`

- [ ] **Step 1: Update index.html — replace pipeline view with in-flight container**

Replace the `#current-card` section (lines 39-51):

```html
  <div id="in-flight-cards" class="in-flight-cards" style="display:none;"></div>
```

This replaces the single-card pipeline step view with a container that JS will populate with all in-flight cards.

- [ ] **Step 2: Update app.js — pollExtractStatus for new status shape**

Replace the `pollExtractStatus` function:

```javascript
async function pollExtractStatus() {
  const [statusResp, cardsResp] = await Promise.all([
    fetch('/api/extract/status'),
    fetch('/api/extract/cards'),
  ]);
  const status = await statusResp.json();
  const allCards = (await cardsResp.json()).cards;

  if (!extractStartTime) extractStartTime = Date.now();

  // Update summary
  const summary = document.getElementById('extract-summary');
  summary.innerHTML =
    '<span>' + status.done.length + ' done</span>' +
    (status.in_flight.length > 0 ? '<span>' + status.in_flight.length + ' in progress</span>' : '') +
    '<span>' + status.queue.length + ' queued</span>' +
    (status.errors.length > 0 ? '<span style="color:#e74c3c;">' + status.errors.length + ' error(s)</span>' : '') +
    '<span id="extract-elapsed" style="margin-left:auto; color:#666;"></span>';

  // Update in-flight cards display
  const inFlightEl = document.getElementById('in-flight-cards');
  if (status.in_flight.length > 0) {
    inFlightEl.style.display = '';
    let html = '';
    status.in_flight.forEach(function(card) {
      const stageLabel = card.stage.replace(/_/g, ' ');
      html += '<div class="in-flight-item">' +
        '<div class="dot"></div>' +
        '<span class="name">' + card.card_id + '</span>' +
        '<span class="label">' + stageLabel + '</span>' +
        '</div>';
    });
    inFlightEl.innerHTML = html;
  } else {
    inFlightEl.style.display = 'none';
  }

  // Build worker status map for card list
  var workerMap = {};
  status.done.forEach(function(name) { workerMap[name] = { icon: 'done', statusText: 'Done' }; });
  status.in_flight.forEach(function(card) {
    var stageLabel = card.stage.replace(/_/g, ' ');
    workerMap[card.card_id] = { icon: 'progress', statusText: stageLabel };
  });
  status.errors.forEach(function(e) { workerMap[e.card_id] = { icon: 'error', statusText: e.reason }; });
  status.queue.forEach(function(name) { workerMap[name] = { icon: 'queued', statusText: 'Queued' }; });

  // Merge: show all cards, overlay worker status on matching ones
  var merged = allCards.map(function(c) {
    var w = workerMap[c.name];
    if (w) return { name: c.name, icon: w.icon, statusText: w.statusText, status: w.icon };
    return { name: c.name, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : c.status, status: c.status };
  });
  renderExtractList(merged);

  // Update total elapsed
  updateTimerDisplay();

  // Check if done
  if (status.status === 'idle' || status.status === 'cancelled') {
    clearInterval(extractPollInterval);
    extractPollInterval = null;
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    extractStartTime = null;
    document.getElementById('extract-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = 'none';
    renderExtractList(merged);
    updateExtractBtn();
    if (status.status === 'cancelled') {
      document.getElementById('extract-summary').innerHTML += '<span style="color:#e67e22;"> (cancelled)</span>';
    }
  }
}
```

- [ ] **Step 3: Simplify timer — remove per-card timer, keep total only**

Remove the `extractCardStartTime`, `lastCurrentCardId` variables and update `updateTimerDisplay`:

```javascript
let extractStartTime = null;
let timerInterval = null;

function formatElapsed(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? m + 'm ' + sec + 's' : sec + 's';
}

function updateTimerDisplay() {
  const totalEl = document.getElementById('extract-elapsed');
  if (totalEl && extractStartTime) {
    totalEl.textContent = 'Total: ' + formatElapsed(Date.now() - extractStartTime);
  }
}
```

Remove these lines that reference deleted variables:
- `let extractCardStartTime = null;`
- `let lastCurrentCardId = null;`

- [ ] **Step 4: Verify UI works — run server and test manually**

Run: `.venv/bin/python -m src.main`
Open browser, go to Extract tab, select cards, start extraction. Verify:
- Multiple cards show as "in progress" simultaneously during OCR
- Summary shows correct counts
- In-flight list displays card names with stage labels
- Timer shows total elapsed

- [ ] **Step 5: Run static tests**

Run: `.venv/bin/python -m pytest tests/test_static.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/web/static/index.html src/web/static/app.js
git commit -m "feat: update extract UI for parallel in-flight cards"
```

---

### Task 5: Run full test suite and final commit

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Fix any failures**

If any tests fail, diagnose and fix. Common issues:
- Tests importing `ExtractionResult` from `pipeline.py` — these should still work since `extract_one` is unchanged
- Tests referencing `status.current` — update to `status.in_flight`

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve remaining test failures from async pipeline"
```
