# Fuzzy Image Matching & Pipeline Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded `" 1"` filename pairing with fuzzy matching, add a Match UI with metadata display, and gate the Extract phase behind confirmed pairs.

**Architecture:** The new `src/images/pairing.py` becomes a fuzzy matching module with metadata reading. A new `src/web/match_state.py` holds in-memory match state (pairs, unmatched, singles, confirmations). The server gains `/match/*` endpoints. The frontend replaces the Merge tab with a Match tab. Stitching is triggered on pair confirmation instead of as a separate batch step.

**Tech Stack:** Python 3.14, difflib, PIL/Pillow, vanilla JS, plain HTTP server.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/images/pairing.py` | **Rewrite**: fuzzy matching algorithm, image metadata reading, normalization, scoring, greedy pairing |
| `src/web/match_state.py` | **New**: in-memory state for the match phase (pairs, unmatched, singles, confirmations, stitch triggering) |
| `src/images/__init__.py` | **Modify**: update public API exports |
| `src/web/server.py` | **Modify**: add `/match/*` endpoints, update `/api/extract` to use match state |
| `src/web/static/index.html` | **Modify**: rename Merge tab → Match, replace merge section HTML |
| `src/web/static/app.js` | **Modify**: replace merge JS with match UI logic |
| `src/web/static/style.css` | **Modify**: add match UI styles |
| `tests/test_pairing.py` | **Rewrite**: test fuzzy matching algorithm |
| `tests/test_match_state.py` | **New**: test match state management |

---

### Task 1: Fuzzy Matching Algorithm — Normalization and Scoring

**Files:**
- Modify: `src/images/pairing.py`
- Test: `tests/test_pairing.py`

- [ ] **Step 1: Write failing tests for normalization**

Replace `tests/test_pairing.py` entirely with:

```python
# tests/test_pairing.py
from src.images.pairing import normalize_filename, similarity_score


def test_normalize_strips_extension():
    assert normalize_filename("photo.jpeg") == "photo"


def test_normalize_lowercases():
    assert normalize_filename("Photo.JPEG") == "photo"


def test_normalize_collapses_whitespace():
    assert normalize_filename("Vanden  Bruelle   Emiel.jpeg") == "vanden bruelle emiel"


def test_normalize_removes_back_suffix_space_1():
    assert normalize_filename("Person Name 1.jpeg") == "person name"


def test_normalize_removes_back_suffix_underscore_back():
    assert normalize_filename("Person_Name_back.jpeg") == "person name"


def test_normalize_removes_achterkant_suffix():
    assert normalize_filename("bidprentje_achterkant.jpeg") == "bidprentje"


def test_similarity_identical_names():
    score = similarity_score("person name 1920", "person name 1920")
    assert score == 100


def test_similarity_front_back_pair():
    score = similarity_score(
        "vanden bruelle emiel jozef haaltert bidprentje 18 december 1928",
        "vanden bruelle emiel jozef haaltert bidprentje 18 december 1928",
    )
    assert score == 100


def test_similarity_partial_overlap():
    score = similarity_score(
        "de smet maria theresia bidprentje",
        "de smet maria bidprentje",
    )
    assert 50 < score < 100


def test_similarity_no_overlap():
    score = similarity_score("aaa bbb ccc", "xxx yyy zzz")
    assert score < 20


def test_similarity_typo_resilience():
    score = similarity_score(
        "pieters jan baptist haaltert 1952",
        "pieters jan batist haaltert 1952",
    )
    assert score > 80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pairing.py -v`
Expected: FAIL — `normalize_filename` and `similarity_score` not found

- [ ] **Step 3: Implement normalization and scoring**

Replace `src/images/pairing.py` entirely with:

```python
# src/images/pairing.py
"""Fuzzy filename matching for front/back image pairs."""

import re
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png"}

_BACK_SUFFIXES = re.compile(
    r"[\s_]*(1|back|achterkant)\s*$", re.IGNORECASE
)


def normalize_filename(filename: str) -> str:
    """Normalize a filename for fuzzy comparison.

    Strips extension, lowercases, removes common back-scan suffixes,
    replaces underscores with spaces, and collapses whitespace.
    """
    stem = Path(filename).stem.lower()
    stem = stem.replace("_", " ")
    stem = _BACK_SUFFIXES.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def similarity_score(name_a: str, name_b: str) -> int:
    """Compute a 0-100 similarity score between two normalized names.

    Combines token overlap (shared words) with sequence similarity
    (handles typos, reordering).
    """
    tokens_a = set(name_a.split())
    tokens_b = set(name_b.split())
    all_tokens = tokens_a | tokens_b

    if not all_tokens:
        return 0

    token_overlap = len(tokens_a & tokens_b) / len(all_tokens)
    sequence_ratio = SequenceMatcher(None, name_a, name_b).ratio()

    combined = (token_overlap * 0.4 + sequence_ratio * 0.6) * 100
    return round(combined)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pairing.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/images/pairing.py tests/test_pairing.py
git commit -m "feat: add fuzzy filename normalization and similarity scoring"
```

---

### Task 2: Image Metadata Reading

**Files:**
- Modify: `src/images/pairing.py`
- Test: `tests/test_pairing.py`

- [ ] **Step 1: Write failing test for metadata reading**

Append to `tests/test_pairing.py`:

```python
from pathlib import Path
from PIL import Image
from src.images.pairing import read_image_metadata


def test_read_image_metadata(tmp_path):
    img_path = tmp_path / "test.jpeg"
    img = Image.new("RGB", (200, 300))
    img.save(img_path, "JPEG")

    meta = read_image_metadata(img_path)

    assert meta["filename"] == "test.jpeg"
    assert meta["width"] == 200
    assert meta["height"] == 300
    assert "dpi" in meta
    assert meta["file_size_bytes"] > 0


def test_read_image_metadata_with_dpi(tmp_path):
    img_path = tmp_path / "hires.jpeg"
    img = Image.new("RGB", (100, 100))
    img.save(img_path, "JPEG", dpi=(300, 300))

    meta = read_image_metadata(img_path)

    assert meta["dpi"] == 300
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `.venv/bin/python -m pytest tests/test_pairing.py::test_read_image_metadata tests/test_pairing.py::test_read_image_metadata_with_dpi -v`
Expected: FAIL — `read_image_metadata` not found

- [ ] **Step 3: Implement metadata reading**

Add to `src/images/pairing.py` (after the existing functions):

```python
def read_image_metadata(image_path: Path) -> dict:
    """Read image metadata: dimensions, DPI, and file size."""
    img = Image.open(image_path)
    width, height = img.size

    dpi_info = img.info.get("dpi")
    dpi = round(dpi_info[0]) if dpi_info else None

    file_size_bytes = image_path.stat().st_size

    return {
        "filename": image_path.name,
        "width": width,
        "height": height,
        "dpi": dpi,
        "file_size_bytes": file_size_bytes,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pairing.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/images/pairing.py tests/test_pairing.py
git commit -m "feat: add image metadata reading (dimensions, DPI, file size)"
```

---

### Task 3: Greedy Pairing (Scan + Match)

**Files:**
- Modify: `src/images/pairing.py`
- Test: `tests/test_pairing.py`

- [ ] **Step 1: Write failing tests for scan_and_match**

Append to `tests/test_pairing.py`:

```python
from src.images.pairing import scan_and_match


def _make_image(path, width=100, height=100):
    """Helper: create a minimal JPEG at the given path."""
    Image.new("RGB", (width, height)).save(path, "JPEG")


def test_scan_and_match_obvious_pair(tmp_path):
    _make_image(tmp_path / "Person A bidprentje 1920.jpeg")
    _make_image(tmp_path / "Person A bidprentje 1920 1.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 1
    assert len(result["unmatched"]) == 0
    pair = result["pairs"][0]
    assert pair["score"] > 80
    assert pair["status"] == "auto_confirmed"


def test_scan_and_match_low_score_not_auto_confirmed(tmp_path):
    _make_image(tmp_path / "aaa bbb ccc.jpeg")
    _make_image(tmp_path / "xxx yyy zzz.jpeg")

    result = scan_and_match(tmp_path)

    # Score too low to pair — both should be unmatched
    assert len(result["unmatched"]) == 2
    assert len(result["pairs"]) == 0


def test_scan_and_match_multiple_pairs_greedy(tmp_path):
    _make_image(tmp_path / "De Smet Maria 1945.jpeg")
    _make_image(tmp_path / "De Smet Maria 1945 1.jpeg")
    _make_image(tmp_path / "Pieters Jan 1952.jpeg")
    _make_image(tmp_path / "Pieters Jan 1952 1.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 2
    assert len(result["unmatched"]) == 0
    names = {
        (p["image_a"]["filename"], p["image_b"]["filename"])
        for p in result["pairs"]
    }
    assert ("De Smet Maria 1945.jpeg", "De Smet Maria 1945 1.jpeg") in names or \
           ("De Smet Maria 1945 1.jpeg", "De Smet Maria 1945.jpeg") in names


def test_scan_and_match_odd_image_out(tmp_path):
    _make_image(tmp_path / "Person A 1920.jpeg")
    _make_image(tmp_path / "Person A 1920 1.jpeg")
    _make_image(tmp_path / "orphan_scan.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 1
    assert len(result["unmatched"]) == 1
    assert result["unmatched"][0]["filename"] == "orphan_scan.jpeg"


def test_scan_and_match_empty_dir(tmp_path):
    result = scan_and_match(tmp_path)

    assert result["pairs"] == []
    assert result["unmatched"] == []


def test_scan_and_match_includes_metadata(tmp_path):
    _make_image(tmp_path / "Card.jpeg", width=200, height=300)
    _make_image(tmp_path / "Card 1.jpeg", width=200, height=300)

    result = scan_and_match(tmp_path)

    pair = result["pairs"][0]
    assert pair["image_a"]["width"] == 200
    assert pair["image_a"]["height"] == 300
    assert pair["image_b"]["width"] == 200
    assert pair["image_b"]["height"] == 300
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `.venv/bin/python -m pytest tests/test_pairing.py::test_scan_and_match_obvious_pair -v`
Expected: FAIL — `scan_and_match` not found

- [ ] **Step 3: Implement scan_and_match**

Add to `src/images/pairing.py` (after existing functions):

```python
_AUTO_CONFIRM_THRESHOLD = 80
_MIN_PAIR_THRESHOLD = 20


def scan_and_match(
    input_dir: Path,
    auto_confirm_threshold: int = _AUTO_CONFIRM_THRESHOLD,
    min_pair_threshold: int = _MIN_PAIR_THRESHOLD,
) -> dict:
    """Scan input directory and return fuzzy-matched pairs with metadata.

    Returns dict with:
        pairs: list of {image_a, image_b, score, status}
        unmatched: list of {filename, width, height, dpi, file_size_bytes}
    """
    files = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not files:
        return {"pairs": [], "unmatched": []}

    # Read metadata and normalize names for all files
    file_info = {}
    for f in files:
        file_info[f.name] = {
            "path": f,
            "normalized": normalize_filename(f.name),
            "metadata": read_image_metadata(f),
        }

    # Build similarity matrix (upper triangle only)
    names = list(file_info.keys())
    scores: list[tuple[int, str, str]] = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            score = similarity_score(
                file_info[name_a]["normalized"],
                file_info[name_b]["normalized"],
            )
            if score >= min_pair_threshold:
                scores.append((score, name_a, name_b))

    # Greedy pairing: highest score first
    scores.sort(reverse=True)
    paired: set[str] = set()
    pairs = []

    for score, name_a, name_b in scores:
        if name_a in paired or name_b in paired:
            continue
        status = "auto_confirmed" if score >= auto_confirm_threshold else "suggested"
        pairs.append({
            "image_a": file_info[name_a]["metadata"],
            "image_b": file_info[name_b]["metadata"],
            "score": score,
            "status": status,
        })
        paired.add(name_a)
        paired.add(name_b)

    # Unmatched: everything not paired
    unmatched = [
        file_info[name]["metadata"]
        for name in names
        if name not in paired
    ]

    # Sort pairs by score ascending (lowest first for UI)
    pairs.sort(key=lambda p: p["score"])

    return {"pairs": pairs, "unmatched": unmatched}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pairing.py -v`
Expected: All 19 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/images/pairing.py tests/test_pairing.py
git commit -m "feat: add greedy fuzzy pairing with metadata and auto-confirm threshold"
```

---

### Task 4: Match State Management

**Files:**
- Create: `src/web/match_state.py`
- Create: `tests/test_match_state.py`

- [ ] **Step 1: Write failing tests for MatchState**

Create `tests/test_match_state.py`:

```python
# tests/test_match_state.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from PIL import Image

from src.web.match_state import MatchState


def _make_image(path, width=100, height=100):
    Image.new("RGB", (width, height)).save(path, "JPEG")


def _make_test_dir(tmp_path):
    """Create a test directory with 2 obvious pairs and 1 orphan."""
    _make_image(tmp_path / "Person A 1920.jpeg")
    _make_image(tmp_path / "Person A 1920 1.jpeg")
    _make_image(tmp_path / "Person B 1950.jpeg")
    _make_image(tmp_path / "Person B 1950 1.jpeg")
    _make_image(tmp_path / "orphan.jpeg")
    return tmp_path


def test_scan_populates_pairs_and_unmatched(tmp_path):
    _make_test_dir(tmp_path)
    state = MatchState(tmp_path, tmp_path / "output")

    result = state.scan()

    assert len(result["pairs"]) == 2
    assert len(result["unmatched"]) == 1


def test_confirm_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    result = state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "confirmed"


def test_unmatch_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()
    state.confirm("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    result = state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    assert result["status"] == "unmatched"
    snapshot = state.get_snapshot()
    # Both images should be in unmatched now
    unmatched_names = {u["filename"] for u in snapshot["unmatched"]}
    assert "Person A 1920.jpeg" in unmatched_names
    assert "Person A 1920 1.jpeg" in unmatched_names


def test_manual_pair(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    # First unmatch a pair to get images into unmatched pool
    state.unmatch("Person A 1920.jpeg", "Person A 1920 1.jpeg")

    result = state.manual_pair("Person A 1920.jpeg", "orphan.jpeg")

    assert result["status"] == "paired"
    snapshot = state.get_snapshot()
    paired_filenames = set()
    for p in snapshot["pairs"]:
        paired_filenames.add(p["image_a"]["filename"])
        paired_filenames.add(p["image_b"]["filename"])
    assert "Person A 1920.jpeg" in paired_filenames
    assert "orphan.jpeg" in paired_filenames


def test_mark_single(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    result = state.mark_single("orphan.jpeg")

    assert result["status"] == "single"
    snapshot = state.get_snapshot()
    assert "orphan.jpeg" in snapshot["singles"]
    unmatched_names = {u["filename"] for u in snapshot["unmatched"]}
    assert "orphan.jpeg" not in unmatched_names


def test_all_resolved_when_confirmed_and_singles(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    # Auto-confirmed pairs count as resolved
    state.mark_single("orphan.jpeg")

    snapshot = state.get_snapshot()
    assert snapshot["all_resolved"] is True


def test_not_all_resolved_with_unmatched(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()

    snapshot = state.get_snapshot()
    # orphan is still unmatched
    assert snapshot["all_resolved"] is False


def test_get_confirmed_pairs_for_extract(tmp_path):
    _make_test_dir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    state = MatchState(tmp_path, output_dir)
    state.scan()
    state.mark_single("orphan.jpeg")

    pairs, singles = state.get_confirmed_items()

    assert len(pairs) == 2
    assert len(singles) == 1
    assert singles[0].name == "orphan.jpeg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_match_state.py -v`
Expected: FAIL — `src.web.match_state` not found

- [ ] **Step 3: Implement MatchState**

Create `src/web/match_state.py`:

```python
# src/web/match_state.py
"""In-memory state management for the match phase."""

import threading
from pathlib import Path

from src.images.pairing import scan_and_match, read_image_metadata, similarity_score, normalize_filename
from src.images.stitching import stitch_pair


class MatchState:
    """Manages match phase state: pairs, unmatched images, singles, confirmations."""

    def __init__(self, input_dir: Path, output_dir: Path):
        self._input_dir = input_dir
        self._output_dir = output_dir
        self._lock = threading.Lock()
        self._pairs: list[dict] = []
        self._unmatched: list[dict] = []
        self._singles: list[str] = []
        self._metadata: dict[str, dict] = {}

    def scan(self) -> dict:
        """Scan input directory and run fuzzy matching. Returns snapshot."""
        result = scan_and_match(self._input_dir)

        with self._lock:
            self._pairs = result["pairs"]
            self._unmatched = result["unmatched"]
            self._singles = []
            self._metadata = {}
            for pair in self._pairs:
                self._metadata[pair["image_a"]["filename"]] = pair["image_a"]
                self._metadata[pair["image_b"]["filename"]] = pair["image_b"]
            for item in self._unmatched:
                self._metadata[item["filename"]] = item

        return self.get_snapshot()

    def get_snapshot(self) -> dict:
        """Return current state as a serializable dict."""
        with self._lock:
            confirmed_count = sum(
                1 for p in self._pairs if p["status"] in ("confirmed", "auto_confirmed")
            )
            needs_review = sum(
                1 for p in self._pairs if p["status"] == "suggested"
            )
            all_resolved = len(self._unmatched) == 0 and needs_review == 0

            return {
                "pairs": [dict(p) for p in self._pairs],
                "unmatched": [dict(u) for u in self._unmatched],
                "singles": list(self._singles),
                "confirmed_count": confirmed_count,
                "needs_review": needs_review,
                "unmatched_count": len(self._unmatched),
                "all_resolved": all_resolved,
            }

    def confirm(self, filename_a: str, filename_b: str) -> dict:
        """Confirm a pair and trigger stitching."""
        with self._lock:
            for pair in self._pairs:
                a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
                if {a, b} == {filename_a, filename_b}:
                    pair["status"] = "confirmed"
                    break
            else:
                return {"status": "not_found"}

        # Stitch in background-safe way (outside lock)
        path_a = self._input_dir / filename_a
        path_b = self._input_dir / filename_b
        output_name = Path(filename_a).stem + ".jpeg"
        output_path = self._output_dir / output_name
        try:
            stitch_pair(path_a, path_b, output_path)
        except Exception:
            pass  # Stitching failure doesn't block confirmation

        return {"status": "confirmed"}

    def unmatch(self, filename_a: str, filename_b: str) -> dict:
        """Break a pair, returning both images to unmatched."""
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
            self._unmatched.append(pair["image_a"])
            self._unmatched.append(pair["image_b"])

        return {"status": "unmatched"}

    def manual_pair(self, filename_a: str, filename_b: str) -> dict:
        """Manually pair two unmatched images."""
        with self._lock:
            meta_a = None
            meta_b = None
            new_unmatched = []

            for item in self._unmatched:
                if item["filename"] == filename_a:
                    meta_a = item
                elif item["filename"] == filename_b:
                    meta_b = item
                else:
                    new_unmatched.append(item)

            if meta_a is None or meta_b is None:
                return {"status": "not_found"}

            self._unmatched = new_unmatched

            norm_a = normalize_filename(filename_a)
            norm_b = normalize_filename(filename_b)
            score = similarity_score(norm_a, norm_b)

            self._pairs.append({
                "image_a": meta_a,
                "image_b": meta_b,
                "score": score,
                "status": "suggested",
            })
            self._pairs.sort(key=lambda p: p["score"])

        return {"status": "paired"}

    def mark_single(self, filename: str) -> dict:
        """Mark an unmatched image as single (no partner)."""
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
            self._singles.append(filename)

        return {"status": "single"}

    def confirm_all(self) -> dict:
        """Confirm all suggested pairs."""
        to_stitch = []
        with self._lock:
            for pair in self._pairs:
                if pair["status"] == "suggested":
                    pair["status"] = "confirmed"
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

    def get_confirmed_items(self) -> tuple[list[tuple[Path, Path]], list[Path]]:
        """Return confirmed pairs and singles as paths for the extract pipeline."""
        with self._lock:
            pairs = []
            for p in self._pairs:
                if p["status"] in ("confirmed", "auto_confirmed"):
                    pairs.append((
                        self._input_dir / p["image_a"]["filename"],
                        self._input_dir / p["image_b"]["filename"],
                    ))
            singles = [self._input_dir / name for name in self._singles]

        return pairs, singles

    def get_scores_for(self, filename: str) -> list[dict]:
        """Get similarity scores between a given file and all other unmatched files."""
        with self._lock:
            others = [u for u in self._unmatched if u["filename"] != filename]

        target_norm = normalize_filename(filename)
        scored = []
        for other in others:
            other_norm = normalize_filename(other["filename"])
            score = similarity_score(target_norm, other_norm)
            scored.append({**other, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_match_state.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/match_state.py tests/test_match_state.py
git commit -m "feat: add MatchState for in-memory match phase management"
```

---

### Task 5: Update Public API Exports

**Files:**
- Modify: `src/images/__init__.py`

- [ ] **Step 1: Update the images package init**

Replace `src/images/__init__.py`:

```python
# src/images/__init__.py
"""Image pairing and stitching for memorial card scans.

Public API:
    scan_and_match   — Fuzzy-match front/back image pairs by filename
    stitch_pair      — Stitch two images side-by-side
    merge_all        — Batch stitch all pairs
"""

from src.images.pairing import scan_and_match
from src.images.stitching import stitch_pair, merge_all

__all__ = ["scan_and_match", "stitch_pair", "merge_all"]
```

- [ ] **Step 2: Commit**

```bash
git add src/images/__init__.py
git commit -m "refactor: update images package exports for fuzzy matching"
```

---

### Task 6: Server — Match Endpoints

**Files:**
- Modify: `src/web/server.py`

- [ ] **Step 1: Update imports and add match state to server**

In `src/web/server.py`, replace the import line:

```python
from src.images import find_pairs, merge_all
```

with:

```python
from src.images.stitching import stitch_pair
from src.web.match_state import MatchState
```

- [ ] **Step 2: Add match endpoints to do_GET**

In `do_GET`, replace the block that handles `/api/merge/pairs` (lines 78-92):

```python
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
```

with:

```python
        elif self.path == "/api/match/scan":
            result = self.server.match_state.scan()
            self._send_json(result)
        elif self.path == "/api/match/state":
            self._send_json(self.server.match_state.get_snapshot())
```

- [ ] **Step 3: Update /api/extract/cards to use match state**

Replace the block at lines 95-106 that handles `/api/extract/cards`:

```python
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
```

with:

```python
        elif self.path == "/api/extract/cards":
            pairs, singles = self.server.match_state.get_confirmed_items()
            cards = []
            for front, back in pairs:
                has_json = (json_dir / f"{front.stem}.json").exists()
                cards.append({
                    "name": front.stem,
                    "front": front.name,
                    "back": back.name,
                    "status": "done" if has_json else "pending",
                })
            for single in singles:
                has_json = (json_dir / f"{single.stem}.json").exists()
                cards.append({
                    "name": single.stem,
                    "front": single.name,
                    "back": None,
                    "status": "done" if has_json else "pending",
                })
            self._send_json({"cards": cards})
```

- [ ] **Step 4: Add match endpoints to do_POST**

Replace the `/api/merge` block (lines 138-153) in `do_POST`:

```python
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
```

with:

```python
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
        elif self.path == "/api/match/scores":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            result = self.server.match_state.get_scores_for(data["filename"])
            self._send_json(result)
```

- [ ] **Step 5: Update /api/extract to use match state instead of find_pairs**

Replace the extract block in `do_POST` (the `elif self.path == "/api/extract":` block). Change these lines:

```python
            cards_filter = options.get("cards", None)
            pairs, _ = find_pairs(input_dir)
            if cards_filter:
                card_set = set(cards_filter)
                pairs = [(f, b) for f, b in pairs if f.stem in card_set]
```

to:

```python
            cards_filter = options.get("cards", None)
            pairs, _singles = self.server.match_state.get_confirmed_items()
            if cards_filter:
                card_set = set(cards_filter)
                pairs = [(f, b) for f, b in pairs if f.stem in card_set]
```

- [ ] **Step 6: Add match_state to make_server**

In `make_server`, add the match state initialization. After `server.worker = ExtractionWorker()`, add:

```python
    server.match_state = MatchState(input_dir, output_dir)
```

- [ ] **Step 7: Commit**

```bash
git add src/web/server.py
git commit -m "feat: add /match/* endpoints and wire extract to match state"
```

---

### Task 7: Frontend — Match Tab HTML and CSS

**Files:**
- Modify: `src/web/static/index.html`
- Modify: `src/web/static/style.css`

- [ ] **Step 1: Update index.html — rename tab and replace merge section**

In `src/web/static/index.html`, replace the navigation:

```html
<nav class="nav-bar">
  <a class="nav-tab" href="#merge" onclick="showSection('merge')">Merge</a>
  <a class="nav-tab" href="#extract" onclick="showSection('extract')">Extract</a>
  <a class="nav-tab" href="#review" onclick="showSection('review')">Review</a>
</nav>
```

with:

```html
<nav class="nav-bar">
  <a class="nav-tab" href="#match" onclick="showSection('match')">Match</a>
  <a class="nav-tab" href="#extract" onclick="showSection('extract')">Extract</a>
  <a class="nav-tab" href="#review" onclick="showSection('review')">Review</a>
</nav>
```

Replace the entire merge section:

```html
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
```

with:

```html
<!-- Match Section -->
<div id="section-match" class="section match-section">
  <div class="match-controls">
    <div class="match-summary" id="match-summary"></div>
    <div class="match-actions">
      <button id="scan-btn" class="btn btn-primary" onclick="scanImages()">Scan Images</button>
      <button id="confirm-all-btn" class="btn btn-primary" onclick="confirmAllPairs()" style="display:none;">Confirm All Pairs</button>
      <button id="proceed-extract-btn" class="btn btn-success" onclick="showSection('extract')" style="display:none;">Proceed to Extract</button>
    </div>
  </div>
  <div id="match-pair-list" class="match-pair-list"></div>
  <div id="match-unmatched" class="match-unmatched"></div>
  <!-- Find Match panel (hidden by default) -->
  <div id="find-match-panel" class="find-match-panel" style="display:none;">
    <div class="find-match-header">
      <h3>Find match for: <span id="find-match-name"></span></h3>
      <button class="btn" onclick="closeFindMatch()">Back to list</button>
    </div>
    <div id="find-match-selected" class="find-match-selected"></div>
    <input type="text" id="find-match-filter" class="find-match-filter" placeholder="Filter by filename..." oninput="filterFindMatch()">
    <div id="find-match-candidates" class="find-match-candidates"></div>
    <div class="find-match-footer">
      <button class="btn btn-danger" onclick="markSingleFromPanel()">Mark as single (no back)</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Add match UI styles to style.css**

Append to `src/web/static/style.css`:

```css
  /* Match section */
  .match-section { padding: 24px; }
  .match-controls { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
  .match-summary { font-size: 14px; display: flex; gap: 16px; }
  .match-summary .confirmed { color: #27ae60; }
  .match-summary .review { color: #e67e22; }
  .match-summary .unmatched-count { color: #e74c3c; }
  .match-actions { display: flex; gap: 8px; }

  .match-pair-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }

  .match-pair-row { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; }
  .match-pair-header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .match-score { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: #fff; }
  .match-score.high { background: #27ae60; }
  .match-score.medium { background: #e67e22; }
  .match-score.low { background: #e74c3c; }
  .match-status-text { font-size: 13px; }
  .match-status-text.auto { color: #27ae60; }
  .match-status-text.review { color: #e67e22; }
  .match-pair-images { display: flex; gap: 16px; align-items: flex-start; }
  .match-image-card { flex: 1; background: #f8f8f8; border-radius: 6px; padding: 10px; }
  .match-image-card img { width: 100%; max-height: 120px; object-fit: contain; border-radius: 4px; background: #eee; }
  .match-image-meta { margin-top: 8px; font-size: 12px; }
  .match-image-meta .filename { color: #333; word-break: break-all; }
  .match-image-meta .details { color: #888; margin-top: 2px; }
  .match-pair-link { display: flex; align-items: center; font-size: 20px; color: #888; padding: 0 8px; }
  .match-pair-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }

  .match-unmatched { margin-top: 8px; }
  .match-unmatched-title { font-size: 14px; font-weight: 600; color: #e74c3c; margin-bottom: 12px; }
  .match-unmatched-grid { display: flex; gap: 10px; flex-wrap: wrap; }
  .match-unmatched-card { background: #fff; border: 1px dashed #e74c3c; border-radius: 6px; padding: 10px; width: 160px; }
  .match-unmatched-card img { width: 100%; max-height: 80px; object-fit: contain; border-radius: 4px; background: #f8f0f0; }
  .match-unmatched-card .filename { font-size: 11px; color: #333; word-break: break-all; margin-top: 6px; }
  .match-unmatched-card .details { font-size: 10px; color: #888; margin-top: 2px; }
  .match-unmatched-card button { margin-top: 6px; width: 100%; }

  /* Find Match panel */
  .find-match-panel { background: #fff; border: 2px solid #4a90d9; border-radius: 8px; padding: 16px; }
  .find-match-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .find-match-header h3 { font-size: 16px; }
  .find-match-selected { background: #f0f7ff; border-radius: 6px; padding: 12px; margin-bottom: 16px; display: flex; align-items: center; gap: 16px; }
  .find-match-selected img { width: 120px; max-height: 80px; object-fit: contain; border-radius: 4px; }
  .find-match-filter { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 12px; }
  .find-match-candidates { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
  .find-match-candidate { display: flex; align-items: center; gap: 12px; padding: 10px; background: #f8f8f8; border-radius: 6px; border: 1px solid #ddd; }
  .find-match-candidate img { width: 80px; max-height: 55px; object-fit: contain; border-radius: 4px; }
  .find-match-candidate .info { flex: 1; font-size: 12px; }
  .find-match-candidate .info .filename { color: #333; }
  .find-match-candidate .info .details { color: #888; margin-top: 2px; }
  .find-match-candidate .score-and-action { display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .find-match-footer { border-top: 1px solid #ddd; padding-top: 12px; }
```

- [ ] **Step 3: Commit**

```bash
git add src/web/static/index.html src/web/static/style.css
git commit -m "feat: add match tab HTML structure and CSS styles"
```

---

### Task 8: Frontend — Match JavaScript Logic

**Files:**
- Modify: `src/web/static/app.js`

- [ ] **Step 1: Replace merge JS with match JS**

In `src/web/static/app.js`, update the `showSection` function. Replace:

```javascript
  if (name === 'merge') await loadMergePairs();
```

with:

```javascript
  if (name === 'match') await loadMatchState();
```

Also update `handleHash`:

```javascript
async function handleHash() {
  const hash = location.hash.slice(1) || 'match';
  if (hash.startsWith('review/')) {
    const cardId = decodeURIComponent(hash.slice(7));
    await showSection('review');
    reviewJumpTo(cardId);
  } else {
    await showSection(hash);
  }
}
```

- [ ] **Step 2: Replace the entire Merge section code**

Remove everything from `/* ---- Merge ---- */` through `triggerMerge()` (lines 30-112). Replace with:

```javascript
/* ---- Match ---- */
let matchData = null;
let findMatchFilename = null;
let findMatchCandidates = [];

async function scanImages() {
  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = 'Scanning...';

  const resp = await fetch('/api/match/scan');
  matchData = await resp.json();

  btn.disabled = false;
  btn.textContent = 'Re-scan';
  renderMatchUI();
}

async function loadMatchState() {
  const resp = await fetch('/api/match/state');
  const data = await resp.json();
  if (data.pairs.length > 0 || data.unmatched.length > 0) {
    matchData = data;
    document.getElementById('scan-btn').textContent = 'Re-scan';
    renderMatchUI();
  }
}

function formatFileSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return bytes + ' B';
}

function formatMeta(meta) {
  var parts = [meta.width + ' \u00d7 ' + meta.height + ' px'];
  if (meta.dpi) parts.push(meta.dpi + ' DPI');
  parts.push(formatFileSize(meta.file_size_bytes));
  return parts.join(' \u00b7 ');
}

function scoreClass(score) {
  if (score >= 80) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function renderMatchUI() {
  if (!matchData) return;

  // Summary
  var summary = document.getElementById('match-summary');
  var parts = [];
  if (matchData.confirmed_count > 0) parts.push('<span class="confirmed">\u2713 ' + matchData.confirmed_count + ' confirmed</span>');
  if (matchData.needs_review > 0) parts.push('<span class="review">\u26a0 ' + matchData.needs_review + ' needs review</span>');
  if (matchData.unmatched_count > 0) parts.push('<span class="unmatched-count">\u2717 ' + matchData.unmatched_count + ' unmatched</span>');
  summary.innerHTML = parts.join(' &middot; ');

  // Show/hide buttons
  document.getElementById('confirm-all-btn').style.display = matchData.needs_review > 0 ? '' : 'none';
  document.getElementById('proceed-extract-btn').style.display = matchData.all_resolved ? '' : 'none';

  // Pair list
  var pairList = document.getElementById('match-pair-list');
  pairList.innerHTML = '';
  matchData.pairs.forEach(function(pair) {
    var row = document.createElement('div');
    row.className = 'match-pair-row';

    var isConfirmed = pair.status === 'confirmed' || pair.status === 'auto_confirmed';
    var statusText = isConfirmed ? '\u2713 Confirmed' : 'Needs review';
    var statusClass = isConfirmed ? 'auto' : 'review';

    row.innerHTML =
      '<div class="match-pair-header">' +
        '<span class="match-score ' + scoreClass(pair.score) + '">' + pair.score + '%</span>' +
        '<span class="match-status-text ' + statusClass + '">' + statusText + '</span>' +
      '</div>' +
      '<div class="match-pair-images">' +
        '<div class="match-image-card">' +
          '<img src="/images/' + encodeURIComponent(pair.image_a.filename) + '" alt="">' +
          '<div class="match-image-meta">' +
            '<div class="filename">' + pair.image_a.filename + '</div>' +
            '<div class="details">' + formatMeta(pair.image_a) + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="match-pair-link">\u27f7</div>' +
        '<div class="match-image-card">' +
          '<img src="/images/' + encodeURIComponent(pair.image_b.filename) + '" alt="">' +
          '<div class="match-image-meta">' +
            '<div class="filename">' + pair.image_b.filename + '</div>' +
            '<div class="details">' + formatMeta(pair.image_b) + '</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="match-pair-actions">' +
        '<button class="btn btn-danger" onclick="unmatchPair(\'' + pair.image_a.filename.replace(/'/g, "\\'") + '\', \'' + pair.image_b.filename.replace(/'/g, "\\'") + '\')">Unmatch</button>' +
        (isConfirmed ? '' : '<button class="btn btn-success" onclick="confirmPair(\'' + pair.image_a.filename.replace(/'/g, "\\'") + '\', \'' + pair.image_b.filename.replace(/'/g, "\\'") + '\')">Confirm \u2713</button>') +
      '</div>';

    pairList.appendChild(row);
  });

  // Unmatched
  var unmatchedDiv = document.getElementById('match-unmatched');
  unmatchedDiv.innerHTML = '';
  if (matchData.unmatched.length > 0) {
    unmatchedDiv.innerHTML = '<div class="match-unmatched-title">Unmatched Images (' + matchData.unmatched.length + ')</div>';
    var grid = document.createElement('div');
    grid.className = 'match-unmatched-grid';
    matchData.unmatched.forEach(function(img) {
      var card = document.createElement('div');
      card.className = 'match-unmatched-card';
      card.innerHTML =
        '<img src="/images/' + encodeURIComponent(img.filename) + '" alt="">' +
        '<div class="filename">' + img.filename + '</div>' +
        '<div class="details">' + formatMeta(img) + '</div>' +
        '<button class="btn btn-primary" style="font-size:11px; padding:4px 8px;" onclick="openFindMatch(\'' + img.filename.replace(/'/g, "\\'") + '\')">Find match...</button>';
      grid.appendChild(card);
    });
    unmatchedDiv.appendChild(grid);
  }

  // Singles
  if (matchData.singles && matchData.singles.length > 0) {
    var singlesTitle = document.createElement('div');
    singlesTitle.className = 'match-unmatched-title';
    singlesTitle.style.color = '#888';
    singlesTitle.style.marginTop = '16px';
    singlesTitle.textContent = 'Singles (' + matchData.singles.length + ')';
    unmatchedDiv.appendChild(singlesTitle);
    var sGrid = document.createElement('div');
    sGrid.className = 'match-unmatched-grid';
    matchData.singles.forEach(function(name) {
      var card = document.createElement('div');
      card.className = 'match-unmatched-card';
      card.style.borderColor = '#888';
      card.innerHTML =
        '<img src="/images/' + encodeURIComponent(name) + '" alt="">' +
        '<div class="filename">' + name + '</div>' +
        '<div class="details" style="color:#888;">Marked as single</div>';
      sGrid.appendChild(card);
    });
    unmatchedDiv.appendChild(sGrid);
  }
}

async function confirmPair(a, b) {
  await fetch('/api/match/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function unmatchPair(a, b) {
  await fetch('/api/match/unmatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function confirmAllPairs() {
  await fetch('/api/match/confirm-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function openFindMatch(filename) {
  findMatchFilename = filename;
  document.getElementById('match-pair-list').style.display = 'none';
  document.getElementById('match-unmatched').style.display = 'none';
  document.getElementById('match-controls') && (document.querySelector('.match-controls').style.display = 'none');

  var panel = document.getElementById('find-match-panel');
  panel.style.display = '';
  document.getElementById('find-match-name').textContent = filename;

  // Show selected image
  var selectedDiv = document.getElementById('find-match-selected');
  selectedDiv.innerHTML =
    '<img src="/images/' + encodeURIComponent(filename) + '" alt="">' +
    '<div><div style="font-weight:600;">' + filename + '</div></div>';

  // Fetch scores
  var resp = await fetch('/api/match/scores', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: filename }),
  });
  findMatchCandidates = await resp.json();

  document.getElementById('find-match-filter').value = '';
  renderFindMatchCandidates(findMatchCandidates);
}

function renderFindMatchCandidates(candidates) {
  var container = document.getElementById('find-match-candidates');
  container.innerHTML = '';
  candidates.forEach(function(c) {
    var div = document.createElement('div');
    div.className = 'find-match-candidate';
    div.innerHTML =
      '<img src="/images/' + encodeURIComponent(c.filename) + '" alt="">' +
      '<div class="info">' +
        '<div class="filename">' + c.filename + '</div>' +
        '<div class="details">' + formatMeta(c) + '</div>' +
      '</div>' +
      '<div class="score-and-action">' +
        '<span class="match-score ' + scoreClass(c.score) + '">' + c.score + '%</span>' +
        '<button class="btn btn-success" style="font-size:11px; padding:3px 10px;" onclick="manualPair(\'' + findMatchFilename.replace(/'/g, "\\'") + '\', \'' + c.filename.replace(/'/g, "\\'") + '\')">Pair</button>' +
      '</div>';
    container.appendChild(div);
  });

  if (candidates.length === 0) {
    container.innerHTML = '<div style="color:#888; padding:16px; text-align:center;">No other unmatched images</div>';
  }
}

function filterFindMatch() {
  var query = document.getElementById('find-match-filter').value.toLowerCase();
  var filtered = findMatchCandidates.filter(function(c) {
    return c.filename.toLowerCase().includes(query);
  });
  renderFindMatchCandidates(filtered);
}

async function manualPair(a, b) {
  await fetch('/api/match/pair', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  closeFindMatch();
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function markSingleFromPanel() {
  await fetch('/api/match/single', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: findMatchFilename }),
  });
  closeFindMatch();
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

function closeFindMatch() {
  document.getElementById('find-match-panel').style.display = 'none';
  document.getElementById('match-pair-list').style.display = '';
  document.getElementById('match-unmatched').style.display = '';
  document.querySelector('.match-controls').style.display = '';
  findMatchFilename = null;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/web/static/app.js
git commit -m "feat: add match tab JavaScript logic (scan, confirm, unmatch, find match)"
```

---

### Task 9: Integration — Wire Extract to Handle Singles

**Files:**
- Modify: `src/web/worker.py`

- [ ] **Step 1: Update worker to handle singles**

The `ExtractionWorker.start()` method currently takes `pairs: list[tuple[Path, Path]]`. Singles need to flow through too. The simplest approach: treat a single as a pair where the back is `None`.

Update the `start` method signature and `_ocr_producer` in `src/web/worker.py`.

In the `_OcrResult` dataclass, make `back_path` and `back_text_path` optional:

```python
@dataclass
class _OcrResult:
    """Internal data passed from OCR stage to LLM stage."""
    card_name: str
    front_path: Path
    back_path: Path | None
    front_text_path: Path
    back_text_path: Path | None
```

In `start`, update the queue_names line to handle optional back:

```python
            queue_names = [front.stem for front, _ in pairs]
```

In `_ocr_producer`, update `ocr_one` to handle `None` back:

```python
    async def ocr_one(front_path: Path, back_path: Path | None):
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
            back_text_path = text_dir / f"{front_path.stem}_back.txt" if back_path else None

            try:
                tasks = [
                    loop.run_in_executor(
                        executor, extract_text,
                        front_path, front_text_path,
                    ),
                ]
                if back_path and back_text_path:
                    tasks.append(
                        loop.run_in_executor(
                            executor, extract_text,
                            back_path, back_text_path,
                        ),
                    )
                await asyncio.gather(*tasks)
            except Exception as e:
                with self._lock:
                    self._remove_in_flight(card_name)
                    self._status.errors.append(
                        CardError(card_name, f"OCR: {e}")
                    )
                return

            with self._lock:
                for p in self._status.in_flight:
                    if p.card_id == card_name:
                        p.stage = "waiting"
                        break

            await ocr_queue.put(_OcrResult(
                card_name=card_name,
                front_path=front_path,
                back_path=back_path,
                front_text_path=front_text_path,
                back_text_path=back_text_path,
            ))
```

In `_llm_consumer`, update date verification to skip back when `None`:

```python
            try:
                verify_items = [(item.front_text_path, item.front_path)]
                if item.back_text_path and item.back_path:
                    verify_items.append((item.back_text_path, item.back_path))
                for txt_path, img_path in verify_items:
                    await loop.run_in_executor(
                        executor, verify_dates,
                        img_path, txt_path, backend, conflicts_dir,
                    )
```

And update interpretation call to handle None back:

```python
            json_output_path = json_dir / f"{card_name}.json"
            back_text = item.back_text_path if item.back_text_path else item.front_text_path
            try:
                await loop.run_in_executor(
                    executor, interpret_text,
                    item.front_text_path, back_text,
                    json_output_path,
                    system_prompt, user_template, backend,
                    item.front_path.name,
                    item.back_path.name if item.back_path else None,
                )
```

- [ ] **Step 2: Update server.py extract handler to pass singles as pairs with None back**

In the `/api/extract` handler in `server.py`, after getting confirmed items:

```python
            pairs, singles = self.server.match_state.get_confirmed_items()
            all_items = pairs + [(s, None) for s in singles]
            if cards_filter:
                card_set = set(cards_filter)
                all_items = [(f, b) for f, b in all_items if f.stem in card_set]
```

And pass `all_items` to `worker.start()` instead of `pairs`.

- [ ] **Step 3: Commit**

```bash
git add src/web/worker.py src/web/server.py
git commit -m "feat: support singles (no back image) in extraction pipeline"
```

---

### Task 10: Manual Testing and Cleanup

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Start the server and manually test**

Run: `.venv/bin/python -m src.web.server` (or however the server is started)

Test the following in the browser:
1. Click "Scan Images" on the Match tab — verify pairs appear with scores and thumbnails
2. Verify score badges are color-coded correctly
3. Click "Unmatch" on a pair — verify both images move to unmatched section
4. Click "Find match..." — verify the panel opens with candidates ranked by score
5. Use the filter bar to narrow candidates
6. Click "Pair" to manually pair two images
7. Click "Mark as single" on an unmatched image
8. Click "Confirm All Pairs" — verify all suggested pairs become confirmed
9. Verify "Proceed to Extract" appears when all images are resolved
10. Navigate to Extract tab — verify only confirmed pairs and singles appear

- [ ] **Step 3: Clean up unused merge code**

Remove any remaining references to the old `find_pairs` function:
- Verify `src/web/server.py` no longer imports `find_pairs` or `merge_all`
- Verify `src/images/__init__.py` no longer exports `find_pairs`
- Remove `merge_all` from `src/images/stitching.py` if no longer used by any code
- Remove `merge_all` from `src/images/__init__.py` exports if removed from stitching.py

- [ ] **Step 4: Run tests one final time**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit cleanup**

```bash
git add -A
git commit -m "chore: remove unused merge code, clean up imports"
```
