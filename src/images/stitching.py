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
