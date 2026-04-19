# tests/test_llm.py
"""Tests for the MLX LLM backend (llm.py)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from PIL import Image

from src.extraction.llm import (
    MLXBackend,
    _strip_code_fences,
    make_backend,
)
from src.extraction.schema import MLX_TEXT_MODEL, MLX_VISION_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pil_image() -> Image.Image:
    """Return a tiny 2x2 white RGB PIL image for testing."""
    return Image.new("RGB", (2, 2), color=(255, 255, 255))


# ---------------------------------------------------------------------------
# MLXBackend — generate_text
# ---------------------------------------------------------------------------


@patch("src.extraction.llm.mlx_lm_generate")
@patch("src.extraction.llm.make_sampler")
@patch("src.extraction.llm.mlx_lm_load")
def test_generate_text_loads_model_lazily(mock_load, mock_sampler, mock_generate):
    """Text model is loaded on first generate_text call, not on construction."""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_load.return_value = (mock_model, mock_tokenizer)
    mock_tokenizer.apply_chat_template.return_value = "formatted"
    mock_generate.return_value = "hello"

    backend = MLXBackend()
    mock_load.assert_not_called()

    backend.generate_text("sys", "user", temperature=0.5, max_tokens=100)
    mock_load.assert_called_once_with(MLX_TEXT_MODEL)


@patch("src.extraction.llm.mlx_lm_generate")
@patch("src.extraction.llm.make_sampler")
@patch("src.extraction.llm.mlx_lm_load")
def test_generate_text_uses_chat_template(mock_load, mock_sampler, mock_generate):
    """System and user prompts are formatted via the tokenizer's chat template."""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_load.return_value = (mock_model, mock_tokenizer)
    mock_tokenizer.apply_chat_template.return_value = "formatted"
    mock_generate.return_value = "result"

    backend = MLXBackend()
    backend.generate_text("sys prompt", "user prompt", temperature=0.0, max_tokens=50)

    mock_tokenizer.apply_chat_template.assert_called_once_with(
        [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "user prompt"},
        ],
        add_generation_prompt=True,
    )


@patch("src.extraction.llm.mlx_lm_generate")
@patch("src.extraction.llm.make_sampler")
@patch("src.extraction.llm.mlx_lm_load")
def test_generate_text_passes_sampling_params(mock_load, mock_sampler, mock_generate):
    """Temperature and max_tokens are forwarded correctly."""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_load.return_value = (mock_model, mock_tokenizer)
    mock_tokenizer.apply_chat_template.return_value = "formatted"
    mock_sampler.return_value = "sampler_obj"
    mock_generate.return_value = "result"

    backend = MLXBackend()
    backend.generate_text("sys", "user", temperature=0.7, max_tokens=512)

    mock_sampler.assert_called_with(temp=0.7)
    mock_generate.assert_called_once_with(
        mock_model,
        mock_tokenizer,
        prompt="formatted",
        max_tokens=512,
        sampler="sampler_obj",
    )


@patch("src.extraction.llm.mlx_lm_generate")
@patch("src.extraction.llm.make_sampler")
@patch("src.extraction.llm.mlx_lm_load")
def test_generate_text_with_json_schema(mock_load, mock_sampler, mock_generate):
    """When json_schema is given, schema is appended to system prompt and fences are stripped."""
    schema = {"type": "object"}
    raw_json = '{"key": "value"}'
    fenced = f"```json\n{raw_json}\n```"

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_load.return_value = (mock_model, mock_tokenizer)
    mock_tokenizer.apply_chat_template.return_value = "formatted"
    mock_generate.return_value = fenced

    backend = MLXBackend()
    result = backend.generate_text("sys", "user", temperature=0.0, max_tokens=50, json_schema=schema)

    assert result == raw_json

    # System message should contain the JSON schema
    messages = mock_tokenizer.apply_chat_template.call_args[0][0]
    system_content = messages[0]["content"]
    assert json.dumps(schema) in system_content
    assert "JSON" in system_content


@patch("src.extraction.llm.mlx_lm_generate")
@patch("src.extraction.llm.make_sampler")
@patch("src.extraction.llm.mlx_lm_load")
def test_generate_text_reuses_loaded_model(mock_load, mock_sampler, mock_generate):
    """Text model is loaded only once across multiple generate_text calls."""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_load.return_value = (mock_model, mock_tokenizer)
    mock_tokenizer.apply_chat_template.return_value = "formatted"
    mock_generate.return_value = "result"

    backend = MLXBackend()
    backend.generate_text("sys", "user", temperature=0.0, max_tokens=10)
    backend.generate_text("sys", "user", temperature=0.0, max_tokens=10)

    mock_load.assert_called_once()


# ---------------------------------------------------------------------------
# MLXBackend — generate_vision
# ---------------------------------------------------------------------------


@patch("src.extraction.llm.mlx_vlm_generate")
@patch("src.extraction.llm.mlx_vlm_apply_chat_template")
@patch("src.extraction.llm.mlx_vlm_load_config")
@patch("src.extraction.llm.mlx_vlm_load")
def test_generate_vision_loads_model_lazily(mock_load, mock_config, mock_template, mock_generate):
    """Vision model is loaded on first generate_vision call, not on construction."""
    mock_model = MagicMock()
    mock_processor = MagicMock()
    mock_load.return_value = (mock_model, mock_processor)
    mock_config.return_value = {}
    mock_template.return_value = "formatted"
    mock_generate.return_value = "1923"

    backend = MLXBackend()
    mock_load.assert_not_called()

    image = _make_pil_image()
    backend.generate_vision("read this", image, temperature=0.0, max_tokens=16)
    mock_load.assert_called_once_with(MLX_VISION_MODEL)


@patch("src.extraction.llm.mlx_vlm_generate")
@patch("src.extraction.llm.mlx_vlm_apply_chat_template")
@patch("src.extraction.llm.mlx_vlm_load_config")
@patch("src.extraction.llm.mlx_vlm_load")
def test_generate_vision_saves_image_and_passes_path(mock_load, mock_config, mock_template, mock_generate):
    """PIL image is saved to a temp file and the path is passed to mlx_vlm.generate."""
    mock_model = MagicMock()
    mock_processor = MagicMock()
    mock_load.return_value = (mock_model, mock_processor)
    mock_config.return_value = {}
    mock_template.return_value = "formatted"
    mock_generate.return_value = "1923"

    backend = MLXBackend()
    image = _make_pil_image()
    result = backend.generate_vision("read this", image, temperature=0.0, max_tokens=16)

    assert result == "1923"
    mock_generate.assert_called_once()
    call_kwargs = mock_generate.call_args
    # image argument should be a list with one string path
    image_arg = call_kwargs[1].get("image") or call_kwargs[0][3]
    assert isinstance(image_arg, list)
    assert len(image_arg) == 1
    assert isinstance(image_arg[0], str)


@patch("src.extraction.llm.mlx_vlm_generate")
@patch("src.extraction.llm.mlx_vlm_apply_chat_template")
@patch("src.extraction.llm.mlx_vlm_load_config")
@patch("src.extraction.llm.mlx_vlm_load")
def test_generate_vision_reuses_loaded_model(mock_load, mock_config, mock_template, mock_generate):
    """Vision model is loaded only once across multiple generate_vision calls."""
    mock_model = MagicMock()
    mock_processor = MagicMock()
    mock_load.return_value = (mock_model, mock_processor)
    mock_config.return_value = {}
    mock_template.return_value = "formatted"
    mock_generate.return_value = "1923"

    backend = MLXBackend()
    image = _make_pil_image()
    backend.generate_vision("read", image, temperature=0.0, max_tokens=16)
    backend.generate_vision("read", image, temperature=0.0, max_tokens=16)

    mock_load.assert_called_once()


# ---------------------------------------------------------------------------
# make_backend factory
# ---------------------------------------------------------------------------


def test_make_backend_defaults_to_mlx(tmp_path):
    """When no config file exists, MLXBackend with default models is returned."""
    config_path = tmp_path / "config.json"
    backend = make_backend(config_path)
    assert isinstance(backend, MLXBackend)
    assert backend._text_model_name == MLX_TEXT_MODEL
    assert backend._vision_model_name == MLX_VISION_MODEL


def test_make_backend_with_custom_models(tmp_path):
    """Config file can override model names."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mlx_text_model": "mlx-community/custom-text",
        "mlx_vision_model": "mlx-community/custom-vision",
    }))

    backend = make_backend(config_path)

    assert isinstance(backend, MLXBackend)
    assert backend._text_model_name == "mlx-community/custom-text"
    assert backend._vision_model_name == "mlx-community/custom-vision"


def test_make_backend_partial_config(tmp_path):
    """Config with only one model override uses defaults for the other."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mlx_text_model": "mlx-community/custom-text",
    }))

    backend = make_backend(config_path)

    assert backend._text_model_name == "mlx-community/custom-text"
    assert backend._vision_model_name == MLX_VISION_MODEL


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
