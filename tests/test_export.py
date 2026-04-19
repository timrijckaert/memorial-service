# tests/test_export.py
import json
from pathlib import Path

from PIL import Image

from src.export import run_export


def _make_image(path, width=100, height=150):
    Image.new("RGB", (width, height)).save(path, "JPEG")


def _make_card_json(json_dir, stem, person, front_image, back_image=None):
    data = {
        "person": person,
        "notes": ["test note"],
        "source": {
            "front_text_file": f"{stem}_front.txt",
            "back_text_file": f"{stem}_back.txt" if back_image else None,
            "front_image_file": front_image,
            "back_image_file": back_image,
        },
    }
    (json_dir / f"{stem}.json").write_text(json.dumps(data))


def test_export_single_card_with_pair(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    _make_image(input_dir / "front.jpeg")
    _make_image(input_dir / "back.jpeg")
    _make_card_json(
        json_dir, "front",
        person={
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "birth_place": "Kerksken",
            "death_date": "1913-12-21",
            "death_place": "Kerksken",
            "birth_date": "1850-03-10",
            "age_at_death": 63,
            "locality": "Kerksken",
            "spouses": [],
        },
        front_image="front.jpeg",
        back_image="back.jpeg",
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1

    # Check stitched image exists
    expected_name = "Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg"
    assert (output_dir / "export" / expected_name).exists()

    # Check consolidated JSON — array of items
    memorial = json.loads((output_dir / "export" / "memorial_cards.json").read_text())
    assert isinstance(memorial, list)
    assert len(memorial) == 1
    card = memorial[0]
    assert card["first_name"] == "Dominicus"
    assert card["last_name"] == "Meganck"
    assert card["notes"] == ["test note"]
    assert card["image_file"] == "Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg"
    # No source metadata in export
    assert "source" not in card
    # Flattened person (no nested "person" key)
    assert "person" not in card


def test_export_single_image_no_back(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    _make_image(input_dir / "single.jpeg")
    _make_card_json(
        json_dir, "single",
        person={
            "first_name": "Frans",
            "last_name": "Van den Bruele",
            "birth_place": "Haaltert",
            "death_date": "1898-01-05",
            "death_place": None,
            "birth_date": None,
            "age_at_death": None,
            "locality": "Haaltert",
            "spouses": [],
        },
        front_image="single.jpeg",
        back_image=None,
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1
    expected_name = "Van den Bruele Frans Haaltert bidprentje 05 januari 1898.jpeg"
    assert (output_dir / "export" / expected_name).exists()


def test_export_filename_collision(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    person = {
        "first_name": "Jan",
        "last_name": "Pieters",
        "birth_place": None,
        "death_date": "1950-06-01",
        "death_place": None,
        "birth_date": None,
        "age_at_death": None,
        "locality": "Haaltert",
        "spouses": [],
    }

    _make_image(input_dir / "card1.jpeg")
    _make_card_json(json_dir, "card1", person=person, front_image="card1.jpeg")

    _make_image(input_dir / "card2.jpeg")
    _make_card_json(json_dir, "card2", person=person, front_image="card2.jpeg")

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 2
    base = "Pieters Jan Haaltert bidprentje 01 juni 1950"
    assert (output_dir / "export" / f"{base}.jpeg").exists()
    assert (output_dir / "export" / f"{base} (2).jpeg").exists()


def test_export_empty_json_dir(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 0
    assert not (output_dir / "export" / "memorial_cards.json").exists()


def test_export_skips_skeleton_only_json(tmp_path):
    """Skeleton JSONs (no person data) are skipped during export."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    json_dir = output_dir / "json"
    json_dir.mkdir()

    # Skeleton-only (from match phase, not yet extracted)
    skeleton = {"source": {"front_image_file": "scan.jpeg", "back_image_file": None}}
    (json_dir / "skeleton-uuid.json").write_text(json.dumps(skeleton))

    # Fully extracted card
    _make_image(input_dir / "front.jpeg")
    _make_card_json(
        json_dir, "extracted-uuid",
        person={"first_name": "Jan", "last_name": "Pieters", "birth_place": None,
                "death_date": "1950-06-01", "death_place": None, "birth_date": None,
                "age_at_death": None, "locality": "Haaltert", "spouses": []},
        front_image="front.jpeg",
    )

    result = run_export(json_dir, input_dir, output_dir)

    assert result["exported"] == 1
