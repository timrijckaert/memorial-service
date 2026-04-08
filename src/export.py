# src/export.py
"""Export phase: stitch images and write consolidated memorial_cards.json."""

import json
import shutil
from pathlib import Path

from src.images.stitching import stitch_pair
from src.naming import derive_filename


def run_export(json_dir: Path, input_dir: Path, output_dir: Path) -> dict:
    """Export all extracted cards to output directory.

    For each card JSON in json_dir:
    - Stitch front+back images (or copy front if no back)
    - Write to output_dir/{derived_filename}.jpeg
    - Collect all cards into output_dir/memorial_cards.json

    Returns dict with 'exported' count.
    """
    card_files = sorted(json_dir.glob("*.json"))
    if not card_files:
        return {"exported": 0}

    export_dir = output_dir / "export"
    export_dir.mkdir(exist_ok=True)

    consolidated: list[dict] = []
    used_names: dict[str, int] = {}

    for card_path in card_files:
        data = json.loads(card_path.read_text())
        if "person" not in data:
            continue  # Skip skeleton-only files
        source = data.get("source", {})
        person = data.get("person", {})
        notes = data.get("notes", [])

        # Derive canonical filename
        base_name = derive_filename(data)

        # Handle collisions
        if base_name in used_names:
            used_names[base_name] += 1
            display_name = f"{base_name} ({used_names[base_name]})"
        else:
            used_names[base_name] = 1
            display_name = base_name

        # Stitch or copy image
        front_file = source.get("front_image_file")
        back_file = source.get("back_image_file")
        output_image = export_dir / f"{display_name}.jpeg"

        if front_file and back_file:
            front_path = input_dir / front_file
            back_path = input_dir / back_file
            if front_path.exists() and back_path.exists():
                stitch_pair(front_path, back_path, output_image)
            elif front_path.exists():
                shutil.copy2(front_path, output_image)
        elif front_file:
            front_path = input_dir / front_file
            if front_path.exists():
                shutil.copy2(front_path, output_image)

        # Build flattened entry for consolidated JSON
        entry = {**person, "notes": notes, "image_file": f"{display_name}.jpeg"}
        consolidated.append(entry)

    # Write consolidated JSON
    memorial_path = export_dir / "memorial_cards.json"
    memorial_path.write_text(
        json.dumps(consolidated, indent=2, ensure_ascii=False)
    )

    return {"exported": len(consolidated)}
