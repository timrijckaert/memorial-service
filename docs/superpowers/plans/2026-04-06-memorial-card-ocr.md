# Memorial Card OCR Text Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract printed Dutch text from front and back memorial card scans using Tesseract OCR, saving results as plain text files alongside the existing stitched images.

**Architecture:** Adds a single `extract_text` function to the existing `src/merge.py` module. The `main()` loop is extended to call OCR on each front/back scan after stitching. `run.sh` gains a Tesseract availability check.

**Tech Stack:** Python 3, Pillow, pytesseract, Tesseract OCR (system binary via Homebrew)

---

## File Structure

- **Modify:** `requirements.txt` — add `pytesseract>=0.3.10`
- **Modify:** `run.sh` — add Tesseract availability check
- **Modify:** `src/merge.py` — add `extract_text` function, update `main()` to run OCR per pair
- **Create:** `tests/test_ocr.py` — tests for `extract_text`

---

### Task 1: Add pytesseract Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytesseract to requirements.txt**

Edit `requirements.txt` to add the new dependency:

```
Pillow>=10.0
pytest>=8.0
pytesseract>=0.3.10
```

- [ ] **Step 2: Reinstall dependencies in the venv**

Run:
```bash
.venv/bin/pip install -r requirements.txt
```

Expected: Successfully installs `pytesseract`. Verify with:
```bash
.venv/bin/python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

This should print the Tesseract version (e.g., `5.5.0`). If it fails with `TesseractNotFoundError`, Tesseract is not installed on the system — run `brew install tesseract tesseract-lang` first.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pytesseract dependency for OCR text extraction"
```

---

### Task 2: Update run.sh with Tesseract Check

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Add Tesseract check to run.sh**

Add a check after the Python check (line 12) and before the venv setup (line 14). The full updated `run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Check Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew: brew install python3"
    exit 1
fi

# Check Tesseract is available
if ! command -v tesseract &>/dev/null; then
    echo "Error: tesseract is required but not found."
    echo "Install it with: brew install tesseract tesseract-lang"
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Run the merge script
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/merge.py"
```

- [ ] **Step 2: Verify the check works**

Run:
```bash
bash run.sh
```

Expected: If Tesseract is installed, the script runs normally. To test the error path, you can temporarily rename the tesseract binary or test with `command -v tesseract` directly.

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "feat: add tesseract availability check to run.sh"
```

---

### Task 3: Write OCR Extraction Tests

**Files:**
- Create: `tests/test_ocr.py`

These tests require Tesseract to be installed on the system. A `skipif` marker skips them gracefully if it's missing.

- [ ] **Step 1: Write the test file with three tests**

Create `tests/test_ocr.py`:

```python
# tests/test_ocr.py
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.merge import extract_text

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract not installed",
)


def _make_text_image(path: Path, text: str) -> Path:
    """Create a white image with black text drawn on it."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=40)
    draw.text((10, 25), text, fill="black", font=font)
    img.save(path, "JPEG")
    return path


def test_extract_text_creates_output_file(tmp_path):
    image_path = _make_text_image(tmp_path / "card.jpeg", "Hello World")
    output_path = tmp_path / "card_front.txt"

    extract_text(image_path, output_path)

    assert output_path.exists()


def test_extract_text_produces_content(tmp_path):
    image_path = _make_text_image(tmp_path / "card.jpeg", "Hello World")
    output_path = tmp_path / "card_front.txt"

    extract_text(image_path, output_path)

    content = output_path.read_text()
    assert len(content) > 0


def test_extract_text_blank_image_creates_file(tmp_path):
    """A blank image with no text should still create the output file."""
    img = Image.new("RGB", (200, 100), "white")
    image_path = tmp_path / "blank.jpeg"
    img.save(image_path, "JPEG")
    output_path = tmp_path / "blank_front.txt"

    extract_text(image_path, output_path)

    assert output_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_ocr.py -v
```

Expected: All 3 tests FAIL with `ImportError: cannot import name 'extract_text' from 'src.merge'` (the function doesn't exist yet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ocr.py
git commit -m "test: add OCR text extraction tests"
```

---

### Task 4: Implement extract_text Function

**Files:**
- Modify: `src/merge.py:1-5` (imports) and add function after `stitch_pair`

- [ ] **Step 1: Add pytesseract import to src/merge.py**

Add `import pytesseract` to the imports at the top of `src/merge.py`:

```python
# src/merge.py
from pathlib import Path
from PIL import Image
import pytesseract
```

- [ ] **Step 2: Add extract_text function after stitch_pair**

Add this function after the `stitch_pair` function (after line 89) and before `main()`:

```python
def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Creates the output file even if no text
    is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(text.strip())
```

- [ ] **Step 3: Run OCR tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_ocr.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 4: Run full test suite to verify nothing broke**

Run:
```bash
.venv/bin/python -m pytest -v
```

Expected: All 15 tests PASS (7 pairing + 5 stitching + 3 OCR).

- [ ] **Step 5: Commit**

```bash
git add src/merge.py
git commit -m "feat: implement OCR text extraction with pytesseract"
```

---

### Task 5: Integrate OCR into Main Pipeline

**Files:**
- Modify: `src/merge.py:92-137` (the `main()` function)

- [ ] **Step 1: Update main() to create text directory and run OCR**

Replace the entire `main()` function in `src/merge.py` with:

```python
def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    text_dir = output_dir / "text"

    if not input_dir.exists():
        input_dir.mkdir()
        print(f"Created {input_dir}/ — drop your scans there and run again.")
        return

    pairs, errors = find_pairs(input_dir)

    if not pairs and not errors:
        print("No scans found in input/. Drop front + back JPEG pairs there and run again.")
        return

    output_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)

    total = len(pairs)
    ok_count = 0
    text_count = 0
    width = len(str(total))

    print(f"Found {len(pairs)} pair{'s' if len(pairs) != 1 else ''} in input/")

    all_errors: list[str] = list(errors)

    for i, (front_path, back_path) in enumerate(pairs, 1):
        output_path = output_dir / front_path.name
        pair_ok = True

        # Stitch
        try:
            stitch_pair(front_path, back_path, output_path)
            ok_count += 1
        except Exception as e:
            all_errors.append(f"{front_path.name} stitch: {e}")
            pair_ok = False

        # OCR
        front_text_path = text_dir / f"{front_path.stem}_front.txt"
        back_text_path = text_dir / f"{back_path.stem}_back.txt"
        try:
            extract_text(front_path, front_text_path)
            extract_text(back_path, back_text_path)
            text_count += 1
        except Exception as e:
            all_errors.append(f"{front_path.name} OCR: {e}")
            pair_ok = False

        # Progress
        if pair_ok:
            print(f"[{i:>{width}}/{total}] {front_path.name}  OK")
        else:
            print(f"[{i:>{width}}/{total}] {front_path.name}  ERROR")

    print(f"\nDone: {ok_count} merged, {text_count} text extracted, {len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    if all_errors:
        print(f"\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")
```

- [ ] **Step 2: Run the full test suite**

Run:
```bash
.venv/bin/python -m pytest -v
```

Expected: All 15 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/merge.py
git commit -m "feat: integrate OCR text extraction into main pipeline"
```

---

### Task 6: Manual Verification

- [ ] **Step 1: Run the full pipeline on real scans**

Run:
```bash
.venv/bin/python src/merge.py
```

Expected output similar to:
```
Found 21 pairs in input/
[ 1/21] Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg  OK
...

Done: 21 merged, 21 text extracted, 0 errors
```

- [ ] **Step 2: Verify text output files exist**

Run:
```bash
ls output/text/ | head -10
```

Expected: Text files with `_front.txt` and `_back.txt` suffixes.

- [ ] **Step 3: Inspect a text file for quality**

Run:
```bash
cat "output/text/$(ls output/text/ | grep _back | head -1)"
```

Expected: Dutch text extracted from the back of a memorial card (names, dates, prayer text).

- [ ] **Step 4: Commit any final adjustments**

If everything looks good, no further commit needed. If minor adjustments were made:

```bash
git add -A
git commit -m "chore: final adjustments after manual OCR verification"
```
