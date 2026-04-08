# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.extraction.interpretation import interpret_text
from src.extraction.schema import PERSON_SCHEMA


SAMPLE_LLM_RESPONSE = json.dumps({
    "person": {
        "first_name": "Dominicus",
        "last_name": "Meganck",
        "birth_date": "1813-12-18",
        "birth_place": "Kerksken",
        "death_date": "1913-12-21",
        "death_place": "Kerksken",
        "age_at_death": None,
        "spouses": ["Amelia Gees"]
    },
    "notes": [
        "birth_place OCR reads 'Kerkxken', normalized to 'Kerksken'",
        "Both birth and death dates are explicit, age_at_death left null"
    ]
})

SYSTEM_PROMPT = "You are a genealogy extraction assistant."

USER_TEMPLATE = (
    "Extract info.\n\n--- FRONT TEXT ---\n{front_text}\n\n--- BACK TEXT ---\n{back_text}"
)


def test_interpret_text_creates_json_file(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Dominicus Meganck geboren 1813")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    assert output.exists()


def test_interpret_text_json_has_required_keys(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("Test text")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


def test_interpret_text_includes_source_filenames(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    result = json.loads(output.read_text())
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card 1_back.txt"


def test_interpret_text_substitutes_placeholders(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Voorkant tekst")
    back_text.write_text("Achterkant tekst")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    user_message = backend.generate_text.call_args.args[1]
    assert "Voorkant tekst" in user_message
    assert "Achterkant tekst" in user_message
    assert "{front_text}" not in user_message
    assert "{back_text}" not in user_message


def test_interpret_text_invalid_json_raises(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = "not valid json at all"

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)


def test_interpret_text_passes_json_schema(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    assert backend.generate_text.call_args.kwargs["json_schema"] == PERSON_SCHEMA


def test_interpret_text_merges_into_existing_skeleton(tmp_path):
    """When output file already exists (skeleton), merge person/notes into it."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Some back text")
    output = tmp_path / "card.json"

    # Pre-create skeleton (simulating what match phase writes)
    skeleton = {
        "source": {
            "front_image_file": "scan_047.jpeg",
            "back_image_file": "scan_047_verso.jpeg",
        }
    }
    output.write_text(json.dumps(skeleton))

    interpret_text(
        front_text, back_text, output,
        SYSTEM_PROMPT, USER_TEMPLATE, backend,
        "scan_047.jpeg", "scan_047_verso.jpeg",
    )

    result = json.loads(output.read_text())
    # Person and notes from LLM response
    assert result["person"]["first_name"] == "Dominicus"
    assert len(result["notes"]) > 0
    # Source preserved from skeleton + text files added
    assert result["source"]["front_image_file"] == "scan_047.jpeg"
    assert result["source"]["back_image_file"] == "scan_047_verso.jpeg"
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card_back.txt"
