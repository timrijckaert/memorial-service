# Codebase Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the flat module layout into a package architecture with clear public APIs, separated concerns, typed dataclasses, and extracted static files.

**Architecture:** Split `src/extract.py` into `src/extraction/` package (7 files), `src/merge.py` into `src/images/` (3 files), `src/review.py` into `src/review/` (2 files), and `src/server.py` into `src/web/` (3 files + 3 static files). Each package exposes a clean `__all__` API via `__init__.py`.

**Tech Stack:** Python 3.14, Pillow, pytesseract, google-genai, pytest

---

## File Map

### New files to create

| File | Responsibility |
|------|---------------|
| `src/extraction/__init__.py` | Re-exports: `extract_one`, `make_gemini_client`, `PERSON_SCHEMA` |
| `src/extraction/schema.py` | `PERSON_SCHEMA` dict, `GEMINI_MODEL` constant |
| `src/extraction/gemini.py` | `make_gemini_client()`, `_call_gemini()`, `_MAX_RETRIES` |
| `src/extraction/ocr.py` | `extract_text()` |
| `src/extraction/date_verification.py` | `verify_dates()`, `_YEAR_RE` |
| `src/extraction/interpretation.py` | `interpret_text()` |
| `src/extraction/pipeline.py` | `ExtractionResult` dataclass, `extract_one()` |
| `src/images/__init__.py` | Re-exports: `find_pairs`, `stitch_pair`, `merge_all` |
| `src/images/pairing.py` | `find_pairs()`, `JPEG_EXTENSIONS` |
| `src/images/stitching.py` | `stitch_pair()`, `merge_all()` |
| `src/review/__init__.py` | Re-exports: `list_cards`, `load_card`, `save_card` |
| `src/review/cards.py` | `list_cards()`, `load_card()`, `save_card()`, `_find_image()` |
| `src/web/__init__.py` | Re-exports: `make_server` |
| `src/web/server.py` | `AppHandler`, `make_server()`, static file serving |
| `src/web/worker.py` | `ExtractionWorker`, `ExtractionStatus`, `CardError` |
| `src/web/static/index.html` | HTML structure with `<link>` and `<script>` tags |
| `src/web/static/style.css` | All CSS (~130 lines) |
| `src/web/static/app.js` | All JS (~465 lines), vanilla |

### Files to modify

| File | Change |
|------|--------|
| `src/main.py` | Update import from `src.server` to `src.web` |
| `tests/test_ocr.py` | Update import path |
| `tests/test_pairing.py` | Update import path |
| `tests/test_stitching.py` | Update import path |
| `tests/test_verify_dates.py` | Fix stale Ollama mocks, update to Gemini API |
| `tests/test_interpret.py` | Fix stale Ollama mocks, update to Gemini API |
| `tests/test_review.py` | Update import path |
| `tests/test_server.py` | Update import and mock paths |

### Files to delete

| File | Replaced by |
|------|------------|
| `src/extract.py` | `src/extraction/` package |
| `src/merge.py` | `src/images/` package |
| `src/review.py` | `src/review/cards.py` |
| `src/server.py` | `src/web/` package |

## Important: Stale tests

`test_verify_dates.py` and `test_interpret.py` currently FAIL because they still mock `src.extract.ollama.chat` but the code was migrated to Gemini. These tests must be fixed as part of the restructure (Task 7). The other 41 tests pass.

---

### Task 1: Create `src/extraction/` package — schema + gemini + ocr

**Files:**
- Create: `src/extraction/__init__.py`
- Create: `src/extraction/schema.py`
- Create: `src/extraction/gemini.py`
- Create: `src/extraction/ocr.py`

- [ ] **Step 1: Create `src/extraction/schema.py`**

```python
# src/extraction/schema.py
"""Shared constants and JSON schema for the extraction pipeline."""

__all__ = ["PERSON_SCHEMA", "GEMINI_MODEL"]

GEMINI_MODEL = "gemini-2.5-flash"

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "nullable": True},
                "last_name": {"type": "string", "nullable": True},
                "birth_date": {"type": "string", "nullable": True},
                "birth_place": {"type": "string", "nullable": True},
                "death_date": {"type": "string", "nullable": True},
                "death_place": {"type": "string", "nullable": True},
                "age_at_death": {"type": "integer", "nullable": True},
                "spouses": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouses",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}
```

- [ ] **Step 2: Create `src/extraction/gemini.py`**

```python
# src/extraction/gemini.py
"""Gemini API client creation and retry wrapper."""

import json
import time
from pathlib import Path

from google import genai
from google.genai.errors import ClientError

__all__ = ["make_gemini_client"]

_MAX_RETRIES = 3


def make_gemini_client(config_path: Path) -> genai.Client:
    """Create a Gemini client from the config file.

    Reads 'gemini_api_key' from the JSON config at config_path.
    """
    config = json.loads(config_path.read_text())
    return genai.Client(api_key=config["gemini_api_key"])


def _call_gemini(client: genai.Client, **kwargs):
    """Call Gemini with automatic retry on rate limit (429) errors.

    Retries up to _MAX_RETRIES times, waiting 60s between attempts
    when a 429 status is received.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(**kwargs)
        except ClientError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                wait = 60
                print(f"        Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
```

- [ ] **Step 3: Create `src/extraction/ocr.py`**

```python
# src/extraction/ocr.py
"""Tesseract OCR text extraction from scanned images."""

from pathlib import Path

from PIL import Image
import pytesseract

__all__ = ["extract_text"]


def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Creates the output file even
    if no text is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    raw = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(raw)
```

- [ ] **Step 4: Create empty `src/extraction/__init__.py` (temporary — will be filled in Task 3)**

```python
# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization."""
```

- [ ] **Step 5: Verify OCR import works**

Run: `.venv/bin/python -c "from src.extraction.ocr import extract_text; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/extraction/
git commit -m "refactor: create extraction/ package with schema, gemini, and ocr modules"
```

---

### Task 2: Create `src/extraction/` package — date_verification + interpretation + pipeline

**Files:**
- Create: `src/extraction/date_verification.py`
- Create: `src/extraction/interpretation.py`
- Create: `src/extraction/pipeline.py`
- Modify: `src/extraction/__init__.py`

- [ ] **Step 1: Create `src/extraction/date_verification.py`**

```python
# src/extraction/date_verification.py
"""Verify OCR-read year digits by visual cross-check with Gemini."""

import re
from pathlib import Path

from PIL import Image
from google import genai
from google.genai import types
import pytesseract

from src.extraction.gemini import _call_gemini
from src.extraction.schema import GEMINI_MODEL

_YEAR_RE = re.compile(r"^\d{4}$")


def verify_dates(
    image_path: Path,
    text_path: Path,
    client: genai.Client,
    conflicts_dir: Path | None = None,
) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking Gemini.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to Gemini for visual verification.
    If Gemini reads a different year, the text file is updated in place and
    the crop image is saved to conflicts_dir for manual review.

    Returns a list of corrections made (empty if all years match).
    """
    image = Image.open(image_path)
    data = pytesseract.image_to_data(
        image, lang="nld", output_type=pytesseract.Output.DICT
    )

    years = _find_year_regions(data)
    if not years:
        return []

    corrections = []
    text = text_path.read_text()

    for entry in years:
        crop = _crop_year_region(image, entry)
        llm_year = _ask_gemini_for_year(client, crop)
        if llm_year is None:
            continue

        if _should_correct(entry["ocr_year"], llm_year):
            text = text.replace(entry["ocr_year"], llm_year, 1)
            corrections.append(f"{entry['ocr_year']} -> {llm_year}")

            if conflicts_dir:
                _save_conflict_crop(conflicts_dir, image_path.stem, entry["ocr_year"], llm_year, crop)

    if corrections:
        text_path.write_text(text)

    return corrections


def _find_year_regions(data: dict) -> list[dict]:
    """Find 4-digit year-like words in Tesseract bounding-box data."""
    years = []
    for i, word in enumerate(data["text"]):
        clean_word = word.strip().rstrip(",.")
        if _YEAR_RE.match(clean_word):
            years.append({
                "ocr_year": clean_word,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            })
    return years


def _crop_year_region(image: Image.Image, entry: dict, pad: int = 10) -> Image.Image:
    """Crop an image region around a detected year word."""
    return image.crop((
        max(0, entry["left"] - pad),
        max(0, entry["top"] - pad),
        entry["left"] + entry["width"] + pad,
        entry["top"] + entry["height"] + pad,
    ))


def _ask_gemini_for_year(client: genai.Client, crop: Image.Image) -> str | None:
    """Send a cropped year image to Gemini and return the read year, or None."""
    resp = _call_gemini(
        client,
        model=GEMINI_MODEL,
        contents=[
            "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
            crop,
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=16,
        ),
    )
    if not resp.text:
        return None
    cleaned = resp.text.strip().rstrip(",.")
    return cleaned if _YEAR_RE.match(cleaned) else None


def _should_correct(ocr_year: str, llm_year: str) -> bool:
    """Check if the LLM year is different from OCR and within valid range (1800-1950)."""
    return llm_year != ocr_year and 1800 <= int(llm_year) <= 1950


def _save_conflict_crop(
    conflicts_dir: Path, stem: str, ocr_year: str, llm_year: str, crop: Image.Image
) -> None:
    """Save a conflict crop image for manual review."""
    conflicts_dir.mkdir(exist_ok=True)
    conflict_path = conflicts_dir / f"{stem}_ocr{ocr_year}_llm{llm_year}.png"
    crop.save(conflict_path)
```

- [ ] **Step 2: Create `src/extraction/interpretation.py`**

```python
# src/extraction/interpretation.py
"""LLM-based interpretation of OCR text into structured biographical data."""

import json
from pathlib import Path

from google import genai
from google.genai import types

from src.extraction.gemini import _call_gemini
from src.extraction.schema import GEMINI_MODEL, PERSON_SCHEMA


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
    client: genai.Client,
) -> None:
    """Interpret OCR text using Gemini and write structured JSON.

    Sends the static system prompt and card-specific user message to Gemini
    with structured JSON output. Writes the parsed JSON to output_path.
    Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    user_message = user_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response = _call_gemini(
        client,
        model=GEMINI_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_json_schema=PERSON_SCHEMA,
        ),
    )

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response.text[:200]}"
        ) from e

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 3: Create `src/extraction/pipeline.py`**

```python
# src/extraction/pipeline.py
"""Orchestrates the full extraction pipeline for a single card pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from google import genai

from src.extraction.ocr import extract_text
from src.extraction.date_verification import verify_dates
from src.extraction.interpretation import interpret_text


@dataclass
class ExtractionResult:
    """Result of processing a single card pair through the extraction pipeline."""
    front_name: str
    ocr_done: bool = False
    verify_corrections: int = 0
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)
    date_fixes: list[str] = field(default_factory=list)


def extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    client: genai.Client | None,
    system_prompt: str | None,
    user_template: str | None,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """Process extraction for a single pair: OCR, date verification, LLM interpretation.

    Pipeline stages (reported via on_step callback):
      1. ocr_front  — Tesseract OCR on front image
      2. ocr_back   — Tesseract OCR on back image
      3. date_verify — Gemini visual cross-check of year digits
      4. llm_extract — Gemini structured data extraction

    Stages 3-4 only run if a Gemini client is provided.
    """
    result = ExtractionResult(front_name=front_path.name)

    front_text_path = text_dir / f"{front_path.stem}_front.txt"
    back_text_path = text_dir / f"{back_path.stem}_back.txt"

    # OCR Front
    if on_step:
        on_step("ocr_front")
    try:
        extract_text(front_path, front_text_path)
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR front: {e}")
        return result

    # OCR Back
    if on_step:
        on_step("ocr_back")
    try:
        extract_text(back_path, back_text_path)
        result.ocr_done = True
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR back: {e}")
        return result

    # Date verification (LLM visual cross-check)
    if client:
        if on_step:
            on_step("date_verify")
        try:
            for txt_path, img_path in [
                (front_text_path, front_path),
                (back_text_path, back_path),
            ]:
                corrections = verify_dates(img_path, txt_path, client, conflicts_dir)
                for c in corrections:
                    result.verify_corrections += 1
                    result.date_fixes.append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result.errors.append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if client:
        if on_step:
            on_step("llm_extract")
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(
                front_text_path, back_text_path, json_output_path,
                system_prompt, user_template, client,
            )
            result.interpreted = True
        except Exception as e:
            result.errors.append(f"{front_path.name} interpret: {e}")

    return result
```

- [ ] **Step 4: Update `src/extraction/__init__.py` with public API**

```python
# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one         — Run the full 4-step pipeline for one card pair
    make_gemini_client  — Create a Gemini API client from config
    PERSON_SCHEMA       — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.gemini import make_gemini_client
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_gemini_client", "PERSON_SCHEMA"]
```

- [ ] **Step 5: Verify extraction package imports work**

Run: `.venv/bin/python -c "from src.extraction import extract_one, make_gemini_client, PERSON_SCHEMA; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/extraction/
git commit -m "refactor: add date_verification, interpretation, and pipeline to extraction package"
```

---

### Task 3: Create `src/images/` package

**Files:**
- Create: `src/images/__init__.py`
- Create: `src/images/pairing.py`
- Create: `src/images/stitching.py`

- [ ] **Step 1: Create `src/images/pairing.py`**

```python
# src/images/pairing.py
"""Detect front/back image pairs based on filename convention."""

from pathlib import Path

JPEG_EXTENSIONS = {".jpeg", ".jpg"}


def find_pairs(input_dir: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Find front/back pairs in input_dir based on filename convention.

    Back scans have ' 1' before the extension. Front scans are the base name.
    Returns (pairs, errors) where pairs is [(front_path, back_path), ...].
    """
    files = list(input_dir.iterdir())

    jpeg_files = {
        f.name: f
        for f in files
        if f.is_file() and f.suffix.lower() in JPEG_EXTENSIONS
    }

    back_files: dict[str, Path] = {}
    front_files: dict[str, Path] = {}

    for name, path in jpeg_files.items():
        stem = path.stem
        if stem.endswith(" 1"):
            back_files[name] = path
        else:
            front_files[name] = path

    # Build normalized lookup for backs: "stem 1" -> path (using lowercase extension)
    back_lookup: dict[str, Path] = {}
    for name, path in back_files.items():
        normalized_key = f"{path.stem}{path.suffix.lower()}"
        back_lookup[normalized_key] = path

    pairs: list[tuple[Path, Path]] = []
    errors: list[str] = []
    matched_backs: set[str] = set()

    for front_name, front_path in sorted(front_files.items()):
        stem = front_path.stem
        ext_lower = front_path.suffix.lower()
        # Try matching with same extension first, then alternate
        for try_ext in [ext_lower] + [e for e in JPEG_EXTENSIONS if e != ext_lower]:
            normalized_back_key = f"{stem} 1{try_ext}"
            if normalized_back_key in back_lookup:
                back_path = back_lookup[normalized_back_key]
                pairs.append((front_path, back_path))
                matched_backs.add(back_path.name)
                break
        else:
            errors.append(f"{front_name}: missing back scan")

    for back_name in sorted(back_files):
        if back_name not in matched_backs:
            errors.append(f"{back_name}: missing front scan")

    return pairs, errors
```

- [ ] **Step 2: Create `src/images/stitching.py`**

```python
# src/images/stitching.py
"""Stitch front/back image pairs side-by-side."""

from pathlib import Path

from PIL import Image


def stitch_pair(front_path: Path, back_path: Path, output_path: Path) -> None:
    """Stitch front and back images side-by-side (front left, back right).

    If heights differ, the shorter image is scaled up to match the taller one.
    Output is JPEG at 85% quality.
    """
    front = Image.open(front_path)
    back = Image.open(back_path)

    target_height = max(front.height, back.height)

    if front.height < target_height:
        scale = target_height / front.height
        front = front.resize(
            (round(front.width * scale), target_height), Image.LANCZOS
        )

    if back.height < target_height:
        scale = target_height / back.height
        back = back.resize(
            (round(back.width * scale), target_height), Image.LANCZOS
        )

    canvas = Image.new("RGB", (front.width + back.width, target_height), "white")
    canvas.paste(front, (0, 0))
    canvas.paste(back, (front.width, 0))
    canvas.save(output_path, "JPEG", quality=85)


def merge_all(
    pairs: list[tuple[Path, Path]],
    output_dir: Path,
    force: bool = False,
) -> tuple[int, int, list[str]]:
    """Stitch all pairs. Returns (ok_count, skipped, errors)."""
    to_process = []
    skipped = 0

    for front_path, back_path in pairs:
        output_path = output_dir / front_path.name
        if not force and output_path.exists():
            skipped += 1
        else:
            to_process.append((front_path, back_path))

    ok_count = 0
    all_errors: list[str] = []
    total = len(to_process)
    width = len(str(total)) if total else 1

    if skipped:
        print(f"Skipping {skipped} already merged")

    for i, (front_path, back_path) in enumerate(to_process, 1):
        output_path = output_dir / front_path.name
        try:
            stitch_pair(front_path, back_path, output_path)
            ok_count += 1
            print(f"  [{i:>{width}}/{total}] {front_path.name}  OK")
        except Exception as e:
            all_errors.append(f"{front_path.name} stitch: {e}")
            print(f"  [{i:>{width}}/{total}] {front_path.name}  ERROR")

    return ok_count, skipped, all_errors
```

- [ ] **Step 3: Create `src/images/__init__.py`**

```python
# src/images/__init__.py
"""Image pairing and stitching for memorial card scans.

Public API:
    find_pairs   — Detect front/back image pairs by filename convention
    stitch_pair  — Stitch two images side-by-side
    merge_all    — Batch stitch all pairs
"""

from src.images.pairing import find_pairs
from src.images.stitching import stitch_pair, merge_all

__all__ = ["find_pairs", "stitch_pair", "merge_all"]
```

- [ ] **Step 4: Verify images package imports work**

Run: `.venv/bin/python -c "from src.images import find_pairs, stitch_pair, merge_all; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/images/
git commit -m "refactor: create images/ package with pairing and stitching modules"
```

---

### Task 4: Create `src/review/` package

**Files:**
- Create: `src/review/__init__.py`
- Create: `src/review/cards.py`

- [ ] **Step 1: Create `src/review/cards.py`**

```python
# src/review/cards.py
"""Card data loading, saving, and listing for the review workflow."""

import json
from pathlib import Path

_JPEG_EXTENSIONS = (".jpeg", ".jpg")


def list_cards(json_dir: Path) -> list[str]:
    """Return sorted list of card ID stems from JSON files in the directory."""
    return sorted(p.stem for p in json_dir.iterdir() if p.suffix == ".json")


def _find_image(input_dir: Path, stem: str) -> str | None:
    """Find a JPEG file matching the given stem in input_dir."""
    for ext in _JPEG_EXTENSIONS:
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

- [ ] **Step 2: Create `src/review/__init__.py`**

```python
# src/review/__init__.py
"""Card data management for the review workflow.

Public API:
    list_cards — List card IDs from JSON directory
    load_card  — Load card data with resolved image paths
    save_card  — Save corrected card data
"""

from src.review.cards import list_cards, load_card, save_card

__all__ = ["list_cards", "load_card", "save_card"]
```

- [ ] **Step 3: Verify review package imports work**

Run: `.venv/bin/python -c "from src.review import list_cards, load_card, save_card; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/review/
git commit -m "refactor: create review/ package with cards module"
```

---

### Task 5: Extract static files from server.py

**Files:**
- Create: `src/web/static/style.css`
- Create: `src/web/static/app.js`
- Create: `src/web/static/index.html`

- [ ] **Step 1: Create `src/web/` and `src/web/static/` directories**

```bash
mkdir -p src/web/static
```

- [ ] **Step 2: Create `src/web/static/style.css`**

Extract the CSS from `server.py` lines 19-128 (contents of the `<style>` tag). Copy the CSS exactly as-is:

```css
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
.pair-images { display: flex; aspect-ratio: 4/3; background: #f0f0f0; }
.pair-images img { flex: 1; object-fit: contain; max-width: 50%; }
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
```

- [ ] **Step 3: Create `src/web/static/app.js`**

Extract the JavaScript from `server.py` lines 217-677 (contents of the `<script>` tag). Copy exactly as-is — the JS is already well-organized with section comments.

The file starts with `/* ---- Navigation ---- */` and ends with `handleHash();`.

Copy the entire JS block unchanged from the `<script>` tag in `server.py`.

- [ ] **Step 4: Create `src/web/static/index.html`**

Replace the inlined `<style>` and `<script>` tags with external file references:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memorial Card Digitizer</title>
<link rel="stylesheet" href="/static/style.css">
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
    <button id="extract-btn" class="btn btn-primary" onclick="triggerExtractSelected()">Extract Selected</button>
    <button id="cancel-btn" class="btn btn-danger" onclick="cancelExtract()" style="display:none;">Cancel</button>
    <label style="cursor:pointer;"><input type="checkbox" id="select-all-extract" onchange="toggleSelectAll(this.checked)"> Select all</label>
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

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 5: Commit**

```bash
git add src/web/static/
git commit -m "refactor: extract HTML, CSS, and JS into separate static files"
```

---

### Task 6: Create `src/web/` package — worker + server

**Files:**
- Create: `src/web/worker.py`
- Create: `src/web/server.py`
- Create: `src/web/__init__.py`

- [ ] **Step 1: Create `src/web/worker.py`**

```python
# src/web/worker.py
"""Background extraction worker thread."""

import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path

from google import genai

from src.extraction import extract_one


@dataclass
class CardError:
    """An error that occurred during extraction of a single card."""
    card_id: str
    reason: str


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    current: dict | None = None
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)


class ExtractionWorker:
    """Runs extraction sequentially on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._status = ExtractionStatus(status="idle")

    def get_status(self) -> ExtractionStatus:
        """Return a snapshot copy of the current status."""
        with self._lock:
            return ExtractionStatus(
                status=self._status.status,
                current=dict(self._status.current) if self._status.current else None,
                done=list(self._status.done),
                errors=[CardError(e.card_id, e.reason) for e in self._status.errors],
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
        client: genai.Client | None,
    ) -> bool:
        """Start extraction on a background thread. Returns False if already running."""
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._status = ExtractionStatus(
                status="running",
                queue=queue_names,
            )
            self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, client),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        """Signal the worker to stop after the current card."""
        self._cancel.set()
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"

    def _run(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        client: genai.Client | None,
    ):
        """Process all pairs sequentially. Runs on a background thread."""
        for front_path, back_path in pairs:
            if self._cancel.is_set():
                with self._lock:
                    self._status.status = "cancelled"
                return

            card_name = front_path.stem

            with self._lock:
                if card_name in self._status.queue:
                    self._status.queue.remove(card_name)
                self._status.current = {"card_id": card_name, "step": "ocr_front"}

            def _on_step(step):
                with self._lock:
                    if self._status.current:
                        self._status.current["step"] = step

            result = extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                client, system_prompt, user_template,
                on_step=_on_step,
            )

            with self._lock:
                if result.errors:
                    self._status.errors.append(
                        CardError(card_id=card_name, reason="; ".join(result.errors))
                    )
                else:
                    self._status.done.append(card_name)
                self._status.current = None

        with self._lock:
            if self._status.status != "cancelled":
                self._status.status = "idle"
```

- [ ] **Step 2: Create `src/web/server.py`**

```python
# src/web/server.py
"""HTTP server for the memorial card web application."""

import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from src.extraction import make_gemini_client
from src.images import find_pairs, merge_all
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
            result = load_card(card_id, json_dir, input_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                self._send_json(result)
        elif self.path.startswith("/images/"):
            filename = unquote(self.path[len("/images/"):])
            self._serve_file(input_dir, filename)
        elif self.path.startswith("/output-images/"):
            filename = unquote(self.path[len("/output-images/"):])
            self._serve_file(output_dir, filename)
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
        elif self.path == "/api/extract/status":
            self._send_json(self.server.worker.get_status().to_dict())
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

            cards_filter = options.get("cards", None)
            pairs, _ = find_pairs(input_dir)
            if cards_filter:
                card_set = set(cards_filter)
                pairs = [(f, b) for f, b in pairs if f.stem in card_set]
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

            # Create Gemini client
            config_path = input_dir.parent / "config.json"
            client = None
            if system_prompt:
                if config_path.exists():
                    try:
                        client = make_gemini_client(config_path)
                    except Exception as e:
                        self._send_json(
                            {"status": "error", "error": f"Failed to create Gemini client: {e}"},
                            503,
                        )
                        return
                else:
                    self._send_json(
                        {"status": "error", "error": "config.json not found. Create it with your Gemini API key."},
                        503,
                    )
                    return

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, client,
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


def make_server(
    json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0
) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    server.worker = ExtractionWorker()
    return server
```

- [ ] **Step 3: Create `src/web/__init__.py`**

```python
# src/web/__init__.py
"""Web server for the memorial card digitizer.

Public API:
    make_server — Create and configure the HTTP server
"""

from src.web.server import make_server

__all__ = ["make_server"]
```

- [ ] **Step 4: Verify web package imports work**

Run: `.venv/bin/python -c "from src.web import make_server; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/web/__init__.py src/web/server.py src/web/worker.py
git commit -m "refactor: create web/ package with server and worker modules"
```

---

### Task 7: Update main.py and all test imports

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_ocr.py`
- Modify: `tests/test_pairing.py`
- Modify: `tests/test_stitching.py`
- Modify: `tests/test_review.py`
- Modify: `tests/test_verify_dates.py` (fix stale Ollama mocks)
- Modify: `tests/test_interpret.py` (fix stale Ollama mocks)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Update `src/main.py`**

Change the import:

```python
# src/main.py
from pathlib import Path
import webbrowser

from src.web import make_server


def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    json_dir = output_dir / "json"

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


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update `tests/test_ocr.py`**

Change one import line:

```python
# Old:
from src.extract import extract_text
# New:
from src.extraction.ocr import extract_text
```

- [ ] **Step 3: Update `tests/test_pairing.py`**

Change one import line:

```python
# Old:
from src.merge import find_pairs
# New:
from src.images.pairing import find_pairs
```

- [ ] **Step 4: Update `tests/test_stitching.py`**

Change one import line:

```python
# Old:
from src.merge import stitch_pair
# New:
from src.images.stitching import stitch_pair
```

- [ ] **Step 5: Update `tests/test_review.py`**

Change one import line:

```python
# Old:
from src.review import list_cards, load_card, save_card
# New:
from src.review.cards import list_cards, load_card, save_card
```

- [ ] **Step 6: Rewrite `tests/test_verify_dates.py`**

The existing tests mock `src.extract.ollama.chat` which no longer exists (migrated to Gemini). Rewrite to mock `_call_gemini` and match the current function signatures:

```python
# tests/test_verify_dates.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw

from src.extraction.date_verification import verify_dates


def _make_image_with_text(tmp_path: Path, text: str, filename: str = "card.jpeg") -> Path:
    """Create a simple image with text for testing."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), text, fill="black")
    path = tmp_path / filename
    img.save(path, "JPEG")
    return path


def _mock_gemini_response(text: str):
    """Create a mock Gemini response with a .text attribute."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_corrects_misread_year(mock_gemini, mock_data, tmp_path):
    """When LLM reads a different year than OCR, the text file is updated."""
    image_path = _make_image_with_text(tmp_path, "overleden 27 Februari 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "27", "Februari", "1944,"],
        "left": [10, 120, 150, 250],
        "top": [40, 40, 40, 40],
        "width": [100, 20, 80, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 86],
    }
    mock_gemini.return_value = _mock_gemini_response("1941")

    corrections = verify_dates(image_path, text_path, mock_client, conflicts_dir)

    assert corrections == ["1944 -> 1941"]
    assert "1941" in text_path.read_text()
    assert "1944" not in text_path.read_text()


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_saves_conflict_image(mock_gemini, mock_data, tmp_path):
    """When OCR and LLM disagree, a crop image is saved for manual review."""
    image_path = _make_image_with_text(tmp_path, "1944", filename="card_back.jpeg")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("den 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["1944,"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [86],
    }
    mock_gemini.return_value = _mock_gemini_response("1941")

    verify_dates(image_path, text_path, mock_client, conflicts_dir)

    assert conflicts_dir.exists()
    conflict_files = list(conflicts_dir.glob("*.png"))
    assert len(conflict_files) == 1
    assert "ocr1944" in conflict_files[0].name
    assert "llm1941" in conflict_files[0].name


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_no_correction_when_matching(mock_gemini, mock_data, tmp_path):
    """When LLM and OCR agree, text is unchanged."""
    image_path = _make_image_with_text(tmp_path, "geboren 15 Juni 1852")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("geboren 15 Juni 1852")
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["geboren", "15", "Juni", "1852"],
        "left": [10, 100, 130, 200],
        "top": [40, 40, 40, 40],
        "width": [80, 20, 40, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 68],
    }
    mock_gemini.return_value = _mock_gemini_response("1852")

    corrections = verify_dates(image_path, text_path, mock_client)

    assert corrections == []
    assert text_path.read_text() == "geboren 15 Juni 1852"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_rejects_llm_year_outside_range(mock_gemini, mock_data, tmp_path):
    """When LLM returns a year outside 1800-1950, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1926")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1926")
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "1926"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }
    mock_gemini.return_value = _mock_gemini_response("2026")

    corrections = verify_dates(image_path, text_path, mock_client)

    assert corrections == []
    assert text_path.read_text() == "overleden 1926"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_years_skips_llm(mock_data, tmp_path):
    """When no year-like words are found, no LLM calls are made."""
    image_path = _make_image_with_text(tmp_path, "no dates here")
    text_path = tmp_path / "card_front.txt"
    text_path.write_text("no dates here")
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["no", "dates", "here"],
        "left": [10, 30, 70],
        "top": [40, 40, 40],
        "width": [15, 35, 30],
        "height": [20, 20, 20],
        "conf": [95, 95, 95],
    }

    corrections = verify_dates(image_path, text_path, mock_client)

    assert corrections == []


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_ignores_invalid_llm_response(mock_gemini, mock_data, tmp_path):
    """When LLM returns non-year text, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1944")
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["overleden", "1944"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }
    mock_gemini.return_value = _mock_gemini_response("The year shown is 1941")

    corrections = verify_dates(image_path, text_path, mock_client)

    assert corrections == []
    assert text_path.read_text() == "overleden 1944"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
@patch("src.extraction.date_verification._call_gemini")
def test_verify_dates_no_stray_crop_files(mock_gemini, mock_data, tmp_path):
    """No stray crop files are left after verification."""
    image_path = _make_image_with_text(tmp_path, "1913")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("1913")
    mock_client = MagicMock()

    mock_data.return_value = {
        "text": ["1913"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [95],
    }
    mock_gemini.return_value = _mock_gemini_response("1913")

    verify_dates(image_path, text_path, mock_client)

    crop_files = list(tmp_path.glob("_crop_*.png"))
    assert crop_files == []
```

- [ ] **Step 7: Rewrite `tests/test_interpret.py`**

The existing tests mock `src.extract.ollama.chat` which no longer exists. Rewrite to mock `_call_gemini` and match the current function signature (`system_prompt` and `user_template` are separate params, `client` is required):

```python
# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.extraction.interpretation import interpret_text


SAMPLE_LLM_RESPONSE = json.dumps({
    "person": {
        "first_name": "Dominicus",
        "last_name": "Meganck",
        "birth_date": "1813-12-18",
        "birth_place": "Kerksken",
        "death_date": "1913-12-21",
        "death_place": "Kerksken",
        "age_at_death": None,
        "spouses": ["Amelia Gees"]
    },
    "notes": [
        "birth_place OCR reads 'Kerkxken', normalized to 'Kerksken'",
        "Both birth and death dates are explicit, age_at_death left null"
    ]
})

SYSTEM_PROMPT = "You are a genealogy extraction assistant."

USER_TEMPLATE = (
    "Extract info.\n\n--- FRONT TEXT ---\n{front_text}\n\n--- BACK TEXT ---\n{back_text}"
)


def _mock_gemini_response(text: str):
    """Create a mock Gemini response with a .text attribute."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_creates_json_file(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Dominicus Meganck geboren 1813")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    assert output.exists()


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_json_has_required_keys(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("Test text")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_includes_source_filenames(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    result = json.loads(output.read_text())
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card 1_back.txt"


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_substitutes_placeholders(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Voorkant tekst")
    back_text.write_text("Achterkant tekst")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    call_args = mock_gemini.call_args
    user_message = call_args.kwargs["contents"]
    assert "Voorkant tekst" in user_message
    assert "Achterkant tekst" in user_message
    assert "{front_text}" not in user_message
    assert "{back_text}" not in user_message


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_invalid_json_raises(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response("not valid json at all")
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)
```

- [ ] **Step 8: Update `tests/test_server.py`**

Two changes needed:
1. Import `make_server` from `src.web.server` instead of `src.server`
2. Mock `extract_one` at `src.web.worker.extract_one` instead of `src.server._extract_one`
3. Mock return value uses `ExtractionResult` dataclass instead of dict

Replace the full file:

```python
# tests/test_server.py
import json
import time
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import pytest
from PIL import Image

from src.extraction.pipeline import ExtractionResult


def _start_test_server(json_dir, input_dir, output_dir, port=0):
    """Start an AppServer on a random port and return (server, base_url)."""
    from src.web.server import make_server

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

    (input_dir / "De Smet Maria.jpeg").write_bytes(b"\xff\xd8front")
    (input_dir / "De Smet Maria 1.jpeg").write_bytes(b"\xff\xd8back")
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
    (output_dir / "Card A.jpeg").write_bytes(b"\xff\xd8merged")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/api/merge/pairs")
        data = json.loads(resp.read())
        assert data["pairs"][0]["merged"] is True
    finally:
        server.shutdown()


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
    _create_test_image(output_dir / "Card A.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with patch("src.web.worker.extract_one") as mock_extract:
            mock_extract.return_value = ExtractionResult(
                front_name="Card A.jpeg",
                ocr_done=True,
                interpreted=True,
            )

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

    for name in ["Card A", "Card B", "Card C"]:
        _create_test_image(input_dir / f"{name}.jpeg", color="red")
        _create_test_image(input_dir / f"{name} 1.jpeg", color="blue")
        _create_test_image(output_dir / f"{name}.jpeg", color="red")

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        def slow_extract(*args, **kwargs):
            time.sleep(0.5)
            return ExtractionResult(
                front_name="test.jpeg",
                ocr_done=True,
                interpreted=True,
            )

        with patch("src.web.worker.extract_one", side_effect=slow_extract):
            req = Request(f"{base}/api/extract", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
            urlopen(req)

            time.sleep(0.2)

            cancel_req = Request(f"{base}/api/extract/cancel", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
            resp = urlopen(cancel_req)
            cancel_data = json.loads(resp.read())
            assert cancel_data["status"] == "cancelling"

            for _ in range(50):
                time.sleep(0.1)
                resp = urlopen(f"{base}/api/extract/status")
                status = json.loads(resp.read())
                if status["status"] == "cancelled":
                    break

            assert status["status"] == "cancelled"
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

- [ ] **Step 9: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests PASS (including the fixed verify_dates and interpret tests).

- [ ] **Step 10: Commit**

```bash
git add src/main.py tests/
git commit -m "refactor: update all imports and fix stale test mocks for new package structure"
```

---

### Task 8: Remove old files and verify

**Files:**
- Delete: `src/extract.py`
- Delete: `src/merge.py`
- Delete: `src/review.py`
- Delete: `src/server.py`

- [ ] **Step 1: Delete old source files**

```bash
git rm src/extract.py src/merge.py src/review.py src/server.py
```

- [ ] **Step 2: Run full test suite to confirm nothing depends on old files**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: remove old flat modules replaced by package structure"
```

---

### Task 9: Add new tests — gemini retry, pipeline orchestration, worker threading, static serving

**Files:**
- Create: `tests/test_gemini.py`
- Create: `tests/test_pipeline.py`
- Create: `tests/test_worker.py`
- Create: `tests/test_static.py`

- [ ] **Step 1: Create `tests/test_gemini.py`**

```python
# tests/test_gemini.py
"""Tests for Gemini API client retry logic."""

from unittest.mock import MagicMock, patch

import pytest

from src.extraction.gemini import _call_gemini, _MAX_RETRIES


def test_call_gemini_returns_on_success():
    """Successful call returns the response directly."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = "response"

    result = _call_gemini(mock_client, model="test", contents="hello")

    assert result == "response"
    assert mock_client.models.generate_content.call_count == 1


def test_call_gemini_retries_on_429():
    """429 errors trigger a retry after waiting."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [error, "success"]

    with patch("src.extraction.gemini.time.sleep") as mock_sleep:
        result = _call_gemini(mock_client, model="test", contents="hello")

    assert result == "success"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once_with(60)


def test_call_gemini_raises_after_max_retries():
    """After _MAX_RETRIES 429 errors, the exception is raised."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [error] * _MAX_RETRIES

    with patch("src.extraction.gemini.time.sleep"):
        with pytest.raises(ClientError):
            _call_gemini(mock_client, model="test", contents="hello")

    assert mock_client.models.generate_content.call_count == _MAX_RETRIES


def test_call_gemini_raises_non_429_immediately():
    """Non-429 errors are raised without retry."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 400
    error.message = "bad request"
    mock_client.models.generate_content.side_effect = error

    with pytest.raises(ClientError):
        _call_gemini(mock_client, model="test", contents="hello")

    assert mock_client.models.generate_content.call_count == 1
```

- [ ] **Step 2: Run gemini tests**

Run: `.venv/bin/python -m pytest tests/test_gemini.py -v`

Expected: All PASS.

- [ ] **Step 3: Create `tests/test_pipeline.py`**

```python
# tests/test_pipeline.py
"""Tests for the extraction pipeline orchestration."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.extraction.pipeline import extract_one, ExtractionResult


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_calls_steps_in_order(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Pipeline calls OCR, date verify, and interpret in order."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_client = MagicMock()
    mock_verify.return_value = []

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_client, "system", "template",
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back", "date_verify", "llm_extract"]
    assert mock_ocr.call_count == 2
    assert mock_verify.call_count == 2
    assert mock_interpret.call_count == 1
    assert result.ocr_done is True
    assert result.interpreted is True
    assert result.errors == []


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_stops_on_ocr_front_failure(mock_ocr, tmp_path):
    """If OCR front fails, the pipeline stops and reports the error."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_ocr.side_effect = RuntimeError("tesseract crashed")

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
    )

    assert result.ocr_done is False
    assert len(result.errors) == 1
    assert "OCR front" in result.errors[0]


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_skips_llm_without_client(mock_ocr, tmp_path):
    """Without a Gemini client, date verify and interpret are skipped."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back"]
    assert result.ocr_done is True
    assert result.interpreted is False


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_reports_date_corrections(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Date corrections are counted and recorded."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_client = MagicMock()
    mock_verify.side_effect = [["1944 -> 1941"], []]

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_client, "system", "template",
    )

    assert result.verify_corrections == 1
    assert len(result.date_fixes) == 1


def test_extraction_result_defaults():
    """ExtractionResult has sensible defaults."""
    result = ExtractionResult(front_name="test.jpeg")

    assert result.front_name == "test.jpeg"
    assert result.ocr_done is False
    assert result.verify_corrections == 0
    assert result.interpreted is False
    assert result.errors == []
    assert result.date_fixes == []
```

- [ ] **Step 4: Run pipeline tests**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`

Expected: All PASS.

- [ ] **Step 5: Create `tests/test_worker.py`**

```python
# tests/test_worker.py
"""Tests for the ExtractionWorker background thread."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.extraction.pipeline import ExtractionResult
from src.web.worker import ExtractionWorker, ExtractionStatus, CardError


def test_worker_starts_idle():
    """New worker starts in idle status."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.current is None
    assert status.done == []
    assert status.errors == []
    assert status.queue == []


@patch("src.web.worker.extract_one")
def test_worker_processes_card(mock_extract, tmp_path):
    """Worker processes a card and moves it to done."""
    mock_extract.return_value = ExtractionResult(
        front_name="Card.jpeg", ocr_done=True, interpreted=True,
    )
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    worker = ExtractionWorker()
    started = worker.start(
        [(front, back)], tmp_path, tmp_path, tmp_path,
        None, None, None,
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "Card" in status.done


@patch("src.web.worker.extract_one")
def test_worker_reports_errors(mock_extract, tmp_path):
    """Worker moves cards with errors to the errors list."""
    mock_extract.return_value = ExtractionResult(
        front_name="Card.jpeg", errors=["OCR failed"],
    )
    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    worker = ExtractionWorker()
    worker.start(
        [(front, back)], tmp_path, tmp_path, tmp_path,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "Card"


def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    worker = ExtractionWorker()

    def slow_extract(*args, **kwargs):
        time.sleep(1)
        return ExtractionResult(front_name="test.jpeg")

    front = tmp_path / "Card.jpeg"
    back = tmp_path / "Card 1.jpeg"
    front.touch()
    back.touch()

    with patch("src.web.worker.extract_one", side_effect=slow_extract):
        worker.start(
            [(front, back)], tmp_path, tmp_path, tmp_path,
            None, None, None,
        )
        second = worker.start(
            [(front, back)], tmp_path, tmp_path, tmp_path,
            None, None, None,
        )

    assert second is False


def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict."""
    status = ExtractionStatus(
        status="running",
        current={"card_id": "test", "step": "ocr_front"},
        done=["card1"],
        errors=[CardError("card2", "failed")],
        queue=["card3"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["current"] == {"card_id": "test", "step": "ocr_front"}
    assert d["done"] == ["card1"]
    assert d["errors"] == [{"card_id": "card2", "reason": "failed"}]
    assert d["queue"] == ["card3"]
```

- [ ] **Step 6: Run worker tests**

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`

Expected: All PASS.

- [ ] **Step 7: Create `tests/test_static.py`**

```python
# tests/test_static.py
"""Tests for static file serving."""

import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


def _start_test_server(json_dir, input_dir, output_dir, port=0):
    from src.web.server import make_server
    server = make_server(json_dir, input_dir, output_dir, port=port)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://localhost:{actual_port}"


def test_static_css_served_with_correct_type(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/static/style.css")
        assert resp.status == 200
        assert "text/css" in resp.headers.get("Content-Type", "")
        body = resp.read().decode()
        assert "nav-bar" in body
    finally:
        server.shutdown()


def test_static_js_served_with_correct_type(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/static/app.js")
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "javascript" in content_type or "text/plain" in content_type
        body = resp.read().decode()
        assert "showSection" in body
    finally:
        server.shutdown()


def test_static_nonexistent_returns_404(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/static/nonexistent.css")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()


def test_static_path_traversal_returns_403(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/static/..%2F..%2Fconfig.json")
        assert exc_info.value.code == 403
    finally:
        server.shutdown()


def test_root_serves_index_html(tmp_path):
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
        assert 'href="/static/style.css"' in body
        assert 'src="/static/app.js"' in body
    finally:
        server.shutdown()
```

- [ ] **Step 8: Run static tests**

Run: `.venv/bin/python -m pytest tests/test_static.py -v`

Expected: All PASS.

- [ ] **Step 9: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add tests/
git commit -m "test: add tests for gemini retry, pipeline orchestration, worker threading, and static serving"
```
