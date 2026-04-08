# src/images/pairing.py
"""Fuzzy filename matching for front/back image pairs."""

import re
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png"}

_BACK_SUFFIXES = re.compile(
    r"[\s_]+(\(2\)|1|2|back|achterkant|verso|b)\s*$", re.IGNORECASE
)


def is_back_image(filename: str) -> bool:
    """Check if a filename looks like a back-side scan."""
    stem = Path(filename).stem
    return bool(_BACK_SUFFIXES.search(stem))


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
        # Put the back image in image_b (front = image_a)
        front, back = name_a, name_b
        if is_back_image(name_a) and not is_back_image(name_b):
            front, back = name_b, name_a
        pairs.append({
            "image_a": file_info[front]["metadata"],
            "image_b": file_info[back]["metadata"],
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
