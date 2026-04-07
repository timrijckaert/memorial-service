# tests/test_llm.py
"""Tests for the LLM backend abstraction (llm.py)."""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image

from src.extraction.llm import (
    GeminiBackend,
    OllamaBackend,
    _strip_code_fences,
    make_backend,
)
from src.extraction.schema import GEMINI_MODEL, OLLAMA_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pil_image() -> Image.Image:
    """Return a tiny 2×2 white RGB PIL image for testing."""
    return Image.new("RGB", (2, 2), color=(255, 255, 255))


def _make_ollama_response(content: str):
    """Build a minimal mock that looks like an ollama ChatResponse."""
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


# ---------------------------------------------------------------------------
# OllamaBackend — generate_text
# ---------------------------------------------------------------------------


def test_ollama_generate_text():
    """chat() is called with the correct model, messages, and options."""
    with patch("src.extraction.llm.chat") as mock_chat:
        mock_chat.return_value = _make_ollama_response("hello")
        backend = OllamaBackend()
        result = backend.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.5,
            max_tokens=100,
        )

    assert result == "hello"
    mock_chat.assert_called_once_with(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        options={"temperature": 0.5, "num_predict": 100},
    )


def test_ollama_generate_text_with_json_schema():
    """When json_schema is given, schema is appended to system prompt and fences are stripped."""
    schema = {"type": "object"}
    raw_json = '{"key": "value"}'
    fenced = f"```json\n{raw_json}\n```"

    with patch("src.extraction.llm.chat") as mock_chat:
        mock_chat.return_value = _make_ollama_response(fenced)
        backend = OllamaBackend()
        result = backend.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.0,
            max_tokens=50,
            json_schema=schema,
        )

    assert result == raw_json

    # The system message content should contain the schema
    sent_messages = mock_chat.call_args.kwargs["messages"]
    system_content = sent_messages[0]["content"]
    assert json.dumps(schema) in system_content
    assert "JSON" in system_content


# ---------------------------------------------------------------------------
# OllamaBackend — generate_vision
# ---------------------------------------------------------------------------


def test_ollama_generate_vision():
    """PIL image is converted to PNG bytes and sent via the images param."""
    image = _make_pil_image()

    with patch("src.extraction.llm.chat") as mock_chat:
        mock_chat.return_value = _make_ollama_response("vision result")
        backend = OllamaBackend()
        result = backend.generate_vision(
            prompt="describe",
            image=image,
            temperature=0.1,
            max_tokens=200,
        )

    assert result == "vision result"
    sent_messages = mock_chat.call_args.kwargs["messages"]
    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg["role"] == "user"
    assert msg["content"] == "describe"
    assert "images" in msg
    # Verify the bytes represent a valid PNG
    img_bytes = msg["images"][0]
    buf = io.BytesIO(img_bytes)
    loaded = Image.open(buf)
    assert loaded.format == "PNG"


# ---------------------------------------------------------------------------
# GeminiBackend — generate_text
# ---------------------------------------------------------------------------


def test_gemini_generate_text():
    """generate_content is called with the expected arguments."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = "gemini answer"

    backend = GeminiBackend(client=mock_client)
    result = backend.generate_text(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.7,
        max_tokens=256,
    )

    assert result == "gemini answer"
    assert mock_client.models.generate_content.call_count == 1
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == GEMINI_MODEL
    assert call_kwargs["contents"] == "user"


def test_gemini_generate_text_with_json_schema():
    """response_json_schema is set on the config when json_schema is provided."""
    from google.genai import types

    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = '{"name": "test"}'

    backend = GeminiBackend(client=mock_client)
    result = backend.generate_text(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.0,
        max_tokens=128,
        json_schema=schema,
    )

    assert result == '{"name": "test"}'
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema


def test_gemini_generate_vision():
    """PIL image is passed directly in contents alongside the prompt."""
    image = _make_pil_image()
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = "vision text"

    backend = GeminiBackend(client=mock_client)
    result = backend.generate_vision(
        prompt="what is this",
        image=image,
        temperature=0.2,
        max_tokens=64,
    )

    assert result == "vision text"
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert contents[0] == "what is this"
    assert contents[1] is image


# ---------------------------------------------------------------------------
# GeminiBackend — retry logic
# ---------------------------------------------------------------------------


def test_gemini_retries_on_429():
    """A 429 ClientError triggers exactly one retry after a 60s sleep."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [
        error,
        MagicMock(text="ok"),
    ]

    with patch("src.extraction.llm.time.sleep") as mock_sleep:
        backend = GeminiBackend(client=mock_client)
        result = backend.generate_text(
            system_prompt="s",
            user_prompt="u",
            temperature=0.0,
            max_tokens=10,
        )

    assert result == "ok"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once_with(60)


def test_gemini_raises_non_429_immediately():
    """Non-429 ClientErrors are raised on the first attempt without retrying."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 400
    error.message = "bad request"
    mock_client.models.generate_content.side_effect = error

    with patch("src.extraction.llm.time.sleep") as mock_sleep:
        backend = GeminiBackend(client=mock_client)
        with pytest.raises(ClientError):
            backend.generate_text(
                system_prompt="s",
                user_prompt="u",
                temperature=0.0,
                max_tokens=10,
            )

    assert mock_client.models.generate_content.call_count == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# make_backend factory
# ---------------------------------------------------------------------------


def test_make_backend_defaults_to_ollama(tmp_path):
    """When no config file exists, OllamaBackend with the default model is returned."""
    config_path = tmp_path / "config.json"
    backend = make_backend(config_path)
    assert isinstance(backend, OllamaBackend)
    assert backend._model == OLLAMA_MODEL


def test_make_backend_creates_gemini(tmp_path):
    """A config with backend=gemini returns a GeminiBackend."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"backend": "gemini", "gemini_api_key": "fake-key"})
    )

    with patch("src.extraction.llm.genai.Client") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        backend = make_backend(config_path)

    assert isinstance(backend, GeminiBackend)
    mock_client_cls.assert_called_once_with(api_key="fake-key")


def test_make_backend_creates_ollama_with_custom_model(tmp_path):
    """A config with ollama_model creates OllamaBackend with that model."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"backend": "ollama", "ollama_model": "llama3:8b"}))

    backend = make_backend(config_path)

    assert isinstance(backend, OllamaBackend)
    assert backend._model == "llama3:8b"


# ---------------------------------------------------------------------------
# _strip_code_fences
# ---------------------------------------------------------------------------


def test_strip_code_fences_removes_json_fences():
    """```json ... ``` fences are removed, leaving only the inner content."""
    text = "```json\n{\"key\": 1}\n```"
    assert _strip_code_fences(text) == '{"key": 1}'


def test_strip_code_fences_noop_on_plain():
    """Plain text with no fences is returned unchanged."""
    text = '{"key": 1}'
    assert _strip_code_fences(text) == '{"key": 1}'


def test_strip_code_fences_handles_bare_fences():
    """Bare ``` fences (no language tag) are also removed."""
    text = "```\n{\"key\": 2}\n```"
    assert _strip_code_fences(text) == '{"key": 2}'
