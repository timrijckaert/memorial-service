# tests/test_llm.py
"""Integration tests for the MLX LLM backend (llm.py).

These tests load real models and run real inference. They require:
- MLX models cached in the project's models/ directory
- Set HF_HUB_CACHE to point there (run.sh does this automatically)

Slow (~10-30s total) but catches real issues that mocks miss.
"""

import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from src.extraction.llm import (
    MLXBackend,
    _strip_code_fences,
    make_backend,
)
from src.extraction.schema import MLX_TEXT_MODEL, MLX_VISION_MODEL

# Point HuggingFace to local models/ directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MODELS_DIR = _PROJECT_ROOT / "models"
os.environ["HF_HUB_CACHE"] = str(_MODELS_DIR)

# Skip all integration tests if models aren't downloaded
_has_models = _MODELS_DIR.exists() and any(_MODELS_DIR.iterdir())
requires_models = pytest.mark.skipif(
    not _has_models, reason="MLX models not downloaded (run ./run.sh first)"
)


# ---------------------------------------------------------------------------
# Shared fixture — models load once for the entire module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def backend():
    """Shared MLXBackend instance. Text and vision models lazy-load on first use."""
    return MLXBackend()


# ---------------------------------------------------------------------------
# MLXBackend — generate_text
# ---------------------------------------------------------------------------


@requires_models
def test_generate_text_returns_string(backend):
    """generate_text returns a non-empty string."""
    result = backend.generate_text(
        system_prompt="You are a helpful assistant.",
        user_prompt="Reply with only the word 'hello'.",
        temperature=0.0,
        max_tokens=16,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@requires_models
def test_generate_text_with_json_schema(backend):
    """When json_schema is provided, the response is valid parseable JSON."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    result = backend.generate_text(
        system_prompt="Extract the name from the text.",
        user_prompt="My name is Tim.",
        temperature=0.0,
        max_tokens=64,
        json_schema=schema,
    )
    parsed = json.loads(result)
    assert "name" in parsed


# ---------------------------------------------------------------------------
# MLXBackend — generate_vision
# ---------------------------------------------------------------------------


def _make_number_image(text: str = "1923") -> Image.Image:
    """Create a simple image with a number drawn on it."""
    img = Image.new("RGB", (120, 50), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 10), text, fill=(0, 0, 0))
    return img


@requires_models
def test_generate_vision_returns_string(backend):
    """generate_vision returns a non-empty string from a real image."""
    image = _make_number_image("1923")
    result = backend.generate_vision(
        prompt="Read the number in this image. Reply with ONLY the number, nothing else.",
        image=image,
        temperature=0.0,
        max_tokens=16,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


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
