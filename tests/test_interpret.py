# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.extraction.interpretation import interpret_text


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


def _mock_gemini_response(text: str):
    """Create a mock Gemini response with a .text attribute."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_creates_json_file(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Dominicus Meganck geboren 1813")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    assert output.exists()


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_json_has_required_keys(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("Test text")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_includes_source_filenames(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    result = json.loads(output.read_text())
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card 1_back.txt"


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_substitutes_placeholders(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response(SAMPLE_LLM_RESPONSE)
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Voorkant tekst")
    back_text.write_text("Achterkant tekst")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)

    call_args = mock_gemini.call_args
    user_message = call_args.kwargs["contents"]
    assert "Voorkant tekst" in user_message
    assert "Achterkant tekst" in user_message
    assert "{front_text}" not in user_message
    assert "{back_text}" not in user_message


@patch("src.extraction.interpretation._call_gemini")
def test_interpret_text_invalid_json_raises(mock_gemini, tmp_path):
    mock_gemini.return_value = _mock_gemini_response("not valid json at all")
    mock_client = MagicMock()

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, mock_client)
