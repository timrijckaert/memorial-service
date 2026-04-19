import json
from src.review.cards import list_cards, load_card, save_card


def test_list_cards_returns_sorted_stems(tmp_path):
    (tmp_path / "B card.json").write_text("{}")
    (tmp_path / "A card.json").write_text("{}")
    (tmp_path / "not_json.txt").write_text("")

    result = list_cards(tmp_path)

    assert result == ["A card", "B card"]


def test_list_cards_empty_dir(tmp_path):
    result = list_cards(tmp_path)

    assert result == []


def test_load_card_returns_json_and_image_paths(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    card_data = {
        "person": {"first_name": "Jan", "last_name": "Pansen"},
        "notes": [],
        "source": {
            "front_text_file": "Jan Pansen_front.txt",
            "back_text_file": "Jan Pansen 1_back.txt",
            "front_image_file": "Jan Pansen.jpeg",
            "back_image_file": "Jan Pansen 1.jpeg",
        },
    }
    (json_dir / "Jan Pansen.json").write_text(json.dumps(card_data))

    result = load_card("Jan Pansen", json_dir)

    assert result["data"] == card_data
    assert result["front_image"] == "Jan Pansen.jpeg"
    assert result["back_image"] == "Jan Pansen 1.jpeg"


def test_load_card_missing_json_returns_none(tmp_path):
    result = load_card("nonexistent", tmp_path)

    assert result is None


def test_save_card_overwrites_json(tmp_path):
    original = {"person": {"first_name": "Old"}, "notes": [], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {"person": {"first_name": "New"}, "notes": ["corrected"], "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"}}
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] == "New"


def test_save_card_preserves_source_from_disk(tmp_path):
    original = {"person": {"first_name": "old"}, "notes": [], "source": {"front_text_file": "real_front.txt", "back_text_file": "real_back.txt"}}
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {"person": {"first_name": "new"}, "notes": [], "source": {"front_text_file": "ignored.txt", "back_text_file": "ignored.txt"}}
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["source"]["front_text_file"] == "real_front.txt"
    assert result["source"]["back_text_file"] == "real_back.txt"


def test_save_card_title_cases_names(tmp_path):
    original = {
        "person": {"first_name": "old", "last_name": "old"},
        "notes": [],
        "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"},
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {
        "person": {
            "first_name": "maria josepha",
            "last_name": "van den bruelle",
        },
        "notes": [],
        "source": {},
    }
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] == "Maria Josepha"
    assert result["person"]["last_name"] == "Van Den Bruelle"


def test_save_card_title_cases_uppercase_spouses(tmp_path):
    original = {
        "person": {"first_name": "old", "last_name": "old", "spouses": []},
        "notes": [],
        "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"},
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {
        "person": {
            "first_name": "MARIA",
            "last_name": "MEGANCK",
            "spouses": ["JOSEPHUS VAN DE VELDE", "PETRUS DE SMET"],
        },
        "notes": [],
        "source": {},
    }
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] == "Maria"
    assert result["person"]["last_name"] == "Meganck"
    assert result["person"]["spouses"] == ["Josephus Van De Velde", "Petrus De Smet"]


def test_save_card_title_case_handles_none_names(tmp_path):
    original = {
        "person": {"first_name": None, "last_name": None},
        "notes": [],
        "source": {"front_text_file": "f.txt", "back_text_file": "b.txt"},
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(original))

    updated = {
        "person": {"first_name": None, "last_name": None},
        "notes": [],
        "source": {},
    }
    save_card("card", tmp_path, updated)

    result = json.loads(path.read_text())
    assert result["person"]["first_name"] is None
    assert result["person"]["last_name"] is None
