# Memorial Card Merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge front/back memorial card scans into single side-by-side JPEG images.

**Architecture:** A single Python script (`src/merge.py`) with two core functions — pairing (filename matching) and stitching (image composition). A shell wrapper (`run.sh`) handles venv setup so the user runs one command. Tests use pytest with small synthetic images created by Pillow.

**Tech Stack:** Python 3.14, Pillow, pytest, venv, bash

---

## File Structure

| File | Responsibility |
|---|---|
| `requirements.txt` | Pillow + pytest dependencies |
| `.gitignore` | Ignore input/, output/, .venv/, __pycache__/ |
| `src/__init__.py` | Empty — makes src a package for imports |
| `src/merge.py` | Pairing logic, stitching logic, CLI entry point |
| `tests/__init__.py` | Empty — makes tests a package |
| `tests/test_pairing.py` | Tests for filename pairing logic |
| `tests/test_stitching.py` | Tests for image stitching logic |
| `run.sh` | Venv setup + script execution wrapper |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Initialize git repo**

Run: `cd /Users/timrijckaert/Documents/memorial-service && git init`
Expected: `Initialized empty Git repository`

- [ ] **Step 2: Create requirements.txt**

```
Pillow>=10.0
pytest>=8.0
```

- [ ] **Step 3: Create .gitignore**

```
input/
output/
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create empty package files**

```bash
mkdir -p src tests
touch src/__init__.py tests/__init__.py
```

- [ ] **Step 5: Set up venv and install dependencies**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: Pillow and pytest install successfully.

- [ ] **Step 6: Verify pytest works**

Run: `.venv/bin/pytest --version`
Expected: `pytest 8.x.x` (or higher)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore src/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding with Pillow and pytest"
```

---

### Task 2: Pairing Logic — Tests

**Files:**
- Create: `tests/test_pairing.py`

All tests create temporary directories with empty files to simulate the filename convention. No real images needed for pairing tests.

- [ ] **Step 1: Write test for successful pairing**

```python
# tests/test_pairing.py
from pathlib import Path
from src.merge import find_pairs


def test_find_pairs_matches_front_and_back(tmp_path):
    front = tmp_path / "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg"
    back = tmp_path / "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928 1.jpeg"
    front.touch()
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 1
    assert pairs[0] == (front, back)
    assert errors == []
```

- [ ] **Step 2: Write test for missing back scan**

```python
def test_find_pairs_reports_missing_back(tmp_path):
    front = tmp_path / "De Smet Maria Aalst  bidprentje 3 maart 1945.jpeg"
    front.touch()

    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert len(errors) == 1
    assert "missing back" in errors[0].lower()
```

- [ ] **Step 3: Write test for missing front scan**

```python
def test_find_pairs_reports_missing_front(tmp_path):
    back = tmp_path / "De Smet Maria Aalst  bidprentje 3 maart 1945 1.jpeg"
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert len(errors) == 1
    assert "missing front" in errors[0].lower()
```

- [ ] **Step 4: Write test for multiple pairs and mixed extensions**

```python
def test_find_pairs_handles_multiple_pairs_and_jpg_extension(tmp_path):
    # Pair 1: .jpeg
    (tmp_path / "Person A  bidprentje 1920.jpeg").touch()
    (tmp_path / "Person A  bidprentje 1920 1.jpeg").touch()
    # Pair 2: .jpg
    (tmp_path / "Person B  bidprentje 1930.jpg").touch()
    (tmp_path / "Person B  bidprentje 1930 1.jpg").touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 2
    assert errors == []
```

- [ ] **Step 5: Write test for case-insensitive extension matching**

```python
def test_find_pairs_handles_uppercase_extension(tmp_path):
    front = tmp_path / "Person C  bidprentje 1940.JPEG"
    back = tmp_path / "Person C  bidprentje 1940 1.JPEG"
    front.touch()
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 1
    assert errors == []
```

- [ ] **Step 6: Write test for empty directory**

```python
def test_find_pairs_empty_directory(tmp_path):
    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert errors == []
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pairing.py -v`
Expected: All tests FAIL with `ImportError: cannot import name 'find_pairs' from 'src.merge'`

- [ ] **Step 8: Commit**

```bash
git add tests/test_pairing.py
git commit -m "test: add pairing logic tests"
```

---

### Task 3: Pairing Logic — Implementation

**Files:**
- Create: `src/merge.py`

- [ ] **Step 1: Implement find_pairs**

```python
# src/merge.py
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
        ext = path.suffix
        if stem.endswith(" 1"):
            back_files[name] = path
        else:
            front_files[name] = path

    pairs: list[tuple[Path, Path]] = []
    errors: list[str] = []
    matched_backs: set[str] = set()

    for front_name, front_path in sorted(front_files.items()):
        stem = front_path.stem
        ext = front_path.suffix
        back_name = f"{stem} 1{ext}"

        # Try exact match first, then case-insensitive extension
        if back_name in back_files:
            pairs.append((front_path, back_files[back_name]))
            matched_backs.add(back_name)
        else:
            # Try alternative extension case
            alt_ext = ext.swapcase()
            alt_back_name = f"{stem} 1{alt_ext}"
            if alt_back_name in back_files:
                pairs.append((front_path, back_files[alt_back_name]))
                matched_backs.add(alt_back_name)
            else:
                errors.append(f"{front_name}: missing back scan")

    for back_name in sorted(back_files):
        if back_name not in matched_backs:
            errors.append(f"{back_name}: missing front scan")

    return pairs, errors
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pairing.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/merge.py
git commit -m "feat: implement filename pairing logic"
```

---

### Task 4: Stitching Logic — Tests

**Files:**
- Create: `tests/test_stitching.py`

Tests create small synthetic images with Pillow (solid colored rectangles) to verify stitching behavior.

- [ ] **Step 1: Write test for same-height images**

```python
# tests/test_stitching.py
from pathlib import Path
from PIL import Image
from src.merge import stitch_pair


def _make_image(path: Path, width: int, height: int, color: str) -> Path:
    """Create a solid-color test image."""
    img = Image.new("RGB", (width, height), color)
    img.save(path, "JPEG")
    return path


def test_stitch_same_height(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 120, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    assert result.size == (220, 200)
```

- [ ] **Step 2: Write test for different-height images (shorter scaled up)**

```python
def test_stitch_different_heights_scales_shorter(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 80, 100, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    # Back was 80x100, scaled to height 200 -> width becomes 160
    assert result.size == (260, 200)
```

- [ ] **Step 3: Write test for front shorter than back**

```python
def test_stitch_front_shorter_than_back(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 100, "red")
    back = _make_image(tmp_path / "back.jpeg", 120, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    # Front was 100x100, scaled to height 200 -> width becomes 200
    assert result.size == (320, 200)
```

- [ ] **Step 4: Write test that output is JPEG**

```python
def test_stitch_outputs_jpeg(tmp_path):
    front = _make_image(tmp_path / "front.jpeg", 100, 200, "red")
    back = _make_image(tmp_path / "back.jpeg", 100, 200, "blue")
    output = tmp_path / "output.jpeg"

    stitch_pair(front, back, output)

    result = Image.open(output)
    assert result.format == "JPEG"
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stitching.py -v`
Expected: All tests FAIL with `ImportError: cannot import name 'stitch_pair' from 'src.merge'`

- [ ] **Step 6: Commit**

```bash
git add tests/test_stitching.py
git commit -m "test: add stitching logic tests"
```

---

### Task 5: Stitching Logic — Implementation

**Files:**
- Modify: `src/merge.py`

- [ ] **Step 1: Add stitch_pair function to src/merge.py**

Add the following after the `find_pairs` function:

```python
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
```

Also add the PIL import at the top of the file, alongside the existing `from pathlib import Path`:

```python
from PIL import Image
```

- [ ] **Step 2: Run stitching tests**

Run: `.venv/bin/pytest tests/test_stitching.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: All 10 tests PASS (6 pairing + 4 stitching).

- [ ] **Step 4: Commit**

```bash
git add src/merge.py
git commit -m "feat: implement image stitching with height normalization"
```

---

### Task 6: Main Entry Point

**Files:**
- Modify: `src/merge.py`

- [ ] **Step 1: Add main function to src/merge.py**

Add the following at the bottom of `src/merge.py`:

```python
import sys


def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"

    if not input_dir.exists():
        input_dir.mkdir()
        print(f"Created {input_dir}/ — drop your scans there and run again.")
        return

    pairs, errors = find_pairs(input_dir)

    if not pairs and not errors:
        print("No scans found in input/. Drop front + back JPEG pairs there and run again.")
        return

    output_dir.mkdir(exist_ok=True)

    total = len(pairs) + len(errors)
    ok_count = 0
    err_count = len(errors)
    width = len(str(total))

    print(f"Found {len(pairs)} pair{'s' if len(pairs) != 1 else ''} in input/")

    # Print errors for unpaired files first in the sequence
    for i, error in enumerate(errors, 1):
        print(f"[{i:>{width}}/{total}] {error}  ERROR")

    for i, (front_path, back_path) in enumerate(pairs, len(errors) + 1):
        output_path = output_dir / front_path.name
        try:
            stitch_pair(front_path, back_path, output_path)
            print(f"[{i:>{width}}/{total}] {front_path.name}  OK")
            ok_count += 1
        except Exception as e:
            print(f"[{i:>{width}}/{total}] {front_path.name}  ERROR: {e}")
            err_count += 1

    print(f"\nDone: {ok_count} merged, {err_count} error{'s' if err_count != 1 else ''}")

    if err_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Also add the `import sys` at the top of the file alongside the other imports.

- [ ] **Step 2: Test manually with sample images**

Move the existing sample images into `input/`:

```bash
mkdir -p input output
cp "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg" input/
cp "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928 1.jpeg" input/
```

Run: `.venv/bin/python src/merge.py`

Expected output:
```
[1/1] Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg  OK

Done: 1 merged, 0 errors
```

Verify the output image exists and looks correct:
```bash
ls -la output/
open "output/Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg"
```

- [ ] **Step 3: Run all tests to make sure nothing broke**

Run: `.venv/bin/pytest -v`
Expected: All 10 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/merge.py
git commit -m "feat: add main entry point with progress output"
```

---

### Task 7: run.sh Wrapper

**Files:**
- Create: `run.sh`

- [ ] **Step 1: Create run.sh**

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

- [ ] **Step 2: Make it executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Test run.sh from scratch**

Delete the existing venv to verify auto-setup works:

```bash
rm -rf .venv
./run.sh
```

Expected: Venv is created, Pillow installed, merge runs, output produced.

- [ ] **Step 4: Test run.sh second run (venv already exists)**

```bash
./run.sh
```

Expected: Skips setup, runs merge immediately.

- [ ] **Step 5: Commit**

```bash
git add run.sh
git commit -m "feat: add run.sh wrapper with automatic venv setup"
```

---

### Task 8: Final Cleanup

**Files:**
- Review all files

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: All 10 tests PASS.

- [ ] **Step 2: Run the tool end-to-end**

```bash
./run.sh
```

Expected: Processes the sample pair, outputs stitched image.

- [ ] **Step 3: Verify output image visually**

```bash
open "output/Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg"
```

Expected: Photo on left, text on right, flush side-by-side, clean JPEG.

- [ ] **Step 4: Commit any final adjustments**

Only if changes were needed. Otherwise skip this step.
