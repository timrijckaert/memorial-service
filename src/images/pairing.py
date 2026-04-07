# src/images/pairing.py
"""Fuzzy filename matching for front/back image pairs."""

import re
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png"}
JPEG_EXTENSIONS = {".jpeg", ".jpg"}

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
