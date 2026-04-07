import json
from pathlib import Path

JPEG_EXTENSIONS = {".jpeg", ".jpg"}


def list_cards(json_dir: Path) -> list[str]:
    """Return sorted list of card ID stems from JSON files in the directory."""
    return sorted(p.stem for p in json_dir.iterdir() if p.suffix == ".json")


def _find_image(input_dir: Path, stem: str) -> str | None:
    """Find a JPEG file matching the given stem in input_dir."""
    for ext in JPEG_EXTENSIONS:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate.name
    return None


def load_card(card_id: str, json_dir: Path, input_dir: Path) -> dict | None:
    """Load card JSON and resolve front/back image filenames. Returns None if not found."""
    json_path = json_dir / f"{card_id}.json"
    if not json_path.exists():
        return None

    data = json.loads(json_path.read_text())
    front_image = _find_image(input_dir, card_id)
    back_image = _find_image(input_dir, f"{card_id} 1")

    return {
        "data": data,
        "front_image": front_image,
        "back_image": back_image,
    }


def save_card(card_id: str, json_dir: Path, updated_data: dict) -> None:
    """Save corrected card data, preserving the original source field from disk."""
    json_path = json_dir / f"{card_id}.json"
    original = json.loads(json_path.read_text())
    updated_data["source"] = original["source"]
    json_path.write_text(json.dumps(updated_data, indent=2, ensure_ascii=False))
