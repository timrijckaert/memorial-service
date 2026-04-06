# src/merge.py
import sys
from pathlib import Path
from PIL import Image

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
