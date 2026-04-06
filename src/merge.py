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
