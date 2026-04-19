# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.extraction.interpretation import interpret_transcription
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


def test_interpret_transcription_creates_json_file(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck geboren 1813 Kerksken",
        output, SYSTEM_PROMPT, backend,
        front_image_file="card.jpeg", back_image_file="card 1.jpeg",
    )

    assert output.exists()


def test_interpret_transcription_json_has_required_keys(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Test text", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


def test_interpret_transcription_sends_transcription_as_user_prompt(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck geboren te Kerkxken",
        output, SYSTEM_PROMPT, backend,
    )

    user_message = backend.generate_text.call_args.args[1]
    assert "Dominicus Meganck geboren te Kerkxken" in user_message


def test_interpret_transcription_passes_json_schema(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Test text", output, SYSTEM_PROMPT, backend,
    )

    assert backend.generate_text.call_args.kwargs["json_schema"] == PERSON_SCHEMA


def test_interpret_transcription_invalid_json_raises(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = "not valid json at all"
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_transcription(
            "Test text", output, SYSTEM_PROMPT, backend,
        )


def test_interpret_transcription_title_cases_uppercase_names(tmp_path):
    """LLM sometimes returns ALL-CAPS names; these must be title-cased."""
    uppercase_response = json.dumps({
        "person": {
            "first_name": "MARIA JOSEPHA",
            "last_name": "VAN DEN BRUELLE",
            "birth_date": "1880-05-14",
            "birth_place": "Haaltert",
            "death_date": "1950-01-03",
            "death_place": "Haaltert",
            "age_at_death": None,
            "spouses": ["JOSEPHUS VAN DE VELDE"]
        },
        "notes": []
    })
    backend = MagicMock()
    backend.generate_text.return_value = uppercase_response
    output = tmp_path / "card.json"

    interpret_transcription(
        "MARIA JOSEPHA VAN DEN BRUELLE", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert result["person"]["first_name"] == "Maria Josepha"
    assert result["person"]["last_name"] == "Van Den Bruelle"
    assert result["person"]["spouses"] == ["Josephus Van De Velde"]


def test_interpret_transcription_merges_into_existing_skeleton(tmp_path):
    """When output file already exists (skeleton), merge person/notes into it."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    skeleton = {
        "source": {
            "front_image_file": "scan_047.jpeg",
            "back_image_file": "scan_047_verso.jpeg",
        }
    }
    output.write_text(json.dumps(skeleton))

    interpret_transcription(
        "Dominicus Meganck geboren 1813",
        output, SYSTEM_PROMPT, backend,
        front_image_file="scan_047.jpeg",
        back_image_file="scan_047_verso.jpeg",
    )

    result = json.loads(output.read_text())
    assert result["person"]["first_name"] == "Dominicus"
    assert len(result["notes"]) > 0
    assert result["source"]["front_image_file"] == "scan_047.jpeg"
    assert result["source"]["back_image_file"] == "scan_047_verso.jpeg"


def test_interpret_transcription_derives_locality(tmp_path):
    """interpret_transcription should derive locality from death_place/birth_place."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert result["person"]["locality"] == "Kerksken"
