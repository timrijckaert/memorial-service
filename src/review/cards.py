# src/review/cards.py
"""Card data loading, saving, and listing for the review workflow."""

import json
from pathlib import Path

def list_cards(json_dir: Path) -> list[str]:
    """Return sorted list of card ID stems from JSON files in the directory."""
    return sorted(p.stem for p in json_dir.iterdir() if p.suffix == ".json")


def load_card(card_id: str, json_dir: Path) -> dict | None:
    """Load card JSON and resolve front/back image filenames. Returns None if not found."""
    json_path = json_dir / f"{card_id}.json"
    if not json_path.exists():
        return None

    data = json.loads(json_path.read_text())
    source = data.get("source", {})
    front_image = source.get("front_image_file")
    back_image = source.get("back_image_file")

    return {
        "data": data,
        "front_image": front_image,
        "back_image": back_image,
    }


def save_card(card_id: str, json_dir: Path, updated_data: dict) -> None:
    """Save corrected card data, preserving the original source field from disk."""
    json_path = json_dir / f"{card_id}.json"
    original = json.loads(json_path.read_text())
    # Title-case names before saving
    person = updated_data.get("person", {})
    if person:
        for field in ("first_name", "last_name"):
            value = person.get(field)
            if value:
                person[field] = value.title()
        if isinstance(person.get("spouses"), list):
            person["spouses"] = [
                s.title() if isinstance(s, str) else s
                for s in person["spouses"]
            ]
    merged = {**updated_data, "source": original["source"]}
    json_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
