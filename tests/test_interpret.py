# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.extract import interpret_text


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

PROMPT_TEMPLATE = (
    "Extract info.\n\n--- FRONT TEXT ---\n{front_text}\n\n--- BACK TEXT ---\n{back_text}"
)


def _mock_chat_response(content: str):
    """Create a mock ollama ChatResponse."""
    mock_response = MagicMock()
    mock_response.message.content = content
    return mock_response


@patch("src.extract.ollama.chat")
def test_interpret_text_creates_json_file(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Dominicus Meganck geboren 1813")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    assert output.exists()


@patch("src.extract.ollama.chat")
def test_interpret_text_json_has_required_keys(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("Test text")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


@patch("src.extract.ollama.chat")
def test_interpret_text_includes_source_filenames(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    result = json.loads(output.read_text())
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card 1_back.txt"


@patch("src.extract.ollama.chat")
def test_interpret_text_substitutes_placeholders(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Voorkant tekst")
    back_text.write_text("Achterkant tekst")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    call_args = mock_chat.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert "Voorkant tekst" in prompt
    assert "Achterkant tekst" in prompt
    assert "{front_text}" not in prompt
    assert "{back_text}" not in prompt


@patch("src.extract.ollama.chat")
def test_interpret_text_invalid_json_raises(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response("not valid json at all")

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)
