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
