# MLX Backend Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Ollama and Gemini LLM backends with a single MLX backend for in-process local inference on Apple Silicon.

**Architecture:** A new `MLXBackend` class replaces `OllamaBackend` and `GeminiBackend` in `src/extraction/llm.py`. It uses `mlx-lm` for text generation and `mlx-vlm` for vision tasks, both lazy-loaded on first use. The `LLMBackend` protocol is kept for test mocking.

**Tech Stack:** `mlx-lm` (text generation), `mlx-vlm` (vision), Apple MLX framework

**Spec:** `docs/superpowers/specs/2026-04-19-mlx-backend-replacement-design.md`

---

### Task 1: Update schema.py constants

**Files:**
- Modify: `src/extraction/schema.py`

- [ ] **Step 1: Replace model constants**

Replace the contents of `src/extraction/schema.py` with:

```python
# src/extraction/schema.py
"""Shared constants and JSON schema for the extraction pipeline."""

__all__ = ["PERSON_SCHEMA", "MLX_TEXT_MODEL", "MLX_VISION_MODEL"]

MLX_TEXT_MODEL = "mlx-community/gemma-3-4b-it-4bit"
MLX_VISION_MODEL = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "nullable": True},
                "last_name": {"type": "string", "nullable": True},
                "birth_date": {"type": "string", "nullable": True},
                "birth_place": {"type": "string", "nullable": True},
                "death_date": {"type": "string", "nullable": True},
                "death_place": {"type": "string", "nullable": True},
                "age_at_death": {"type": "integer", "nullable": True},
                "spouses": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouses",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}
```

- [ ] **Step 2: Verify no import breakage**

Run: `.venv/bin/python -c "from src.extraction.schema import MLX_TEXT_MODEL, MLX_VISION_MODEL, PERSON_SCHEMA; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/extraction/schema.py
git commit -m "refactor: replace Ollama/Gemini model constants with MLX model constants"
```

---

### Task 2: Write failing tests for MLXBackend.generate_text

**Files:**
- Create: `tests/test_llm.py` (rewrite existing)

- [ ] **Step 1: Write tests for generate_text**

Replace `tests/test_llm.py` with:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm.py -v`

Expected: FAIL — `MLXBackend` does not exist yet, `mlx_lm_generate` etc. not importable.

- [ ] **Step 3: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add failing tests for MLXBackend"
```

---

### Task 3: Implement MLXBackend in llm.py

**Files:**
- Modify: `src/extraction/llm.py` (full rewrite)

- [ ] **Step 1: Rewrite llm.py**

Replace the contents of `src/extraction/llm.py` with:

```python
# src/extraction/llm.py
"""LLM backend abstraction for the extraction pipeline.

Provides a Protocol (LLMBackend) and a single concrete implementation:
  - MLXBackend — runs models in-process via Apple's MLX framework

Use make_backend(config_path) to obtain the backend at runtime.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional, Protocol

from mlx_lm import load as mlx_lm_load, generate as mlx_lm_generate
from mlx_lm.sample_utils import make_sampler
from mlx_vlm import load as mlx_vlm_load, generate as mlx_vlm_generate
from mlx_vlm.prompt_utils import apply_chat_template as mlx_vlm_apply_chat_template
from mlx_vlm.utils import load_config as mlx_vlm_load_config

from src.extraction.schema import MLX_TEXT_MODEL, MLX_VISION_MODEL

__all__ = ["LLMBackend", "MLXBackend", "make_backend"]

_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY valid JSON matching this schema. "
    "No markdown, no explanation, no code fences.\n"
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class LLMBackend(Protocol):
    """Minimal interface expected by the extraction pipeline."""

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Generate a text response given system and user prompts."""
        ...

    def generate_vision(
        self,
        prompt: str,
        image,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate a text response from a prompt and a PIL image."""
        ...


# ---------------------------------------------------------------------------
# MLXBackend
# ---------------------------------------------------------------------------


class MLXBackend:
    """LLM backend that runs models in-process via Apple's MLX framework.

    Uses two separate models:
      - mlx-lm for text generation (generate_text)
      - mlx-vlm for vision tasks (generate_vision)

    Both models are lazy-loaded on first use.
    """

    def __init__(
        self,
        text_model: str = MLX_TEXT_MODEL,
        vision_model: str = MLX_VISION_MODEL,
    ) -> None:
        self._text_model_name = text_model
        self._vision_model_name = vision_model
        self._text_model = None
        self._text_tokenizer = None
        self._vision_model = None
        self._vision_processor = None
        self._vision_config = None

    def _ensure_text_model(self):
        """Load the text model if not already loaded."""
        if self._text_model is None:
            print(f"    Loading text model {self._text_model_name}...")
            self._text_model, self._text_tokenizer = mlx_lm_load(self._text_model_name)

    def _ensure_vision_model(self):
        """Load the vision model if not already loaded."""
        if self._vision_model is None:
            print(f"    Loading vision model {self._vision_model_name}...")
            self._vision_model, self._vision_processor = mlx_vlm_load(self._vision_model_name)
            self._vision_config = mlx_vlm_load_config(self._vision_model_name)

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: Optional[dict] = None,
    ) -> str:
        self._ensure_text_model()

        sys = system_prompt
        if json_schema is not None:
            sys = sys + _JSON_INSTRUCTION + json.dumps(json_schema)

        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user_prompt},
        ]
        prompt = self._text_tokenizer.apply_chat_template(
            messages, add_generation_prompt=True,
        )

        sampler = make_sampler(temp=temperature)
        text = mlx_lm_generate(
            self._text_model,
            self._text_tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
        )

        if json_schema is not None:
            text = _strip_code_fences(text)
        return text

    def generate_vision(
        self,
        prompt: str,
        image,
        temperature: float,
        max_tokens: int,
    ) -> str:
        self._ensure_vision_model()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            image.save(f, format="PNG")
            image_path = f.name

        formatted_prompt = mlx_vlm_apply_chat_template(
            self._vision_processor,
            self._vision_config,
            prompt,
            num_images=1,
        )

        result = mlx_vlm_generate(
            self._vision_model,
            self._vision_processor,
            formatted_prompt,
            image=[image_path],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_backend(config_path: Path) -> LLMBackend:
    """Create an MLXBackend, optionally with model overrides from config.

    If config_path does not exist, returns MLXBackend with default models.
    """
    if not config_path.exists():
        return MLXBackend()
    config = json.loads(config_path.read_text())
    return MLXBackend(
        text_model=config.get("mlx_text_model", MLX_TEXT_MODEL),
        vision_model=config.get("mlx_vision_model", MLX_VISION_MODEL),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove surrounding markdown code fences from *text*, if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm.py -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/extraction/llm.py
git commit -m "feat: replace Ollama/Gemini backends with MLXBackend"
```

---

### Task 4: Update extraction package exports

**Files:**
- Modify: `src/extraction/__init__.py`

- [ ] **Step 1: Update exports**

Replace the contents of `src/extraction/__init__.py` with:

```python
# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one  — Run the full 4-step pipeline for one card pair
    make_backend — Create an LLM backend from config
    LLMBackend   — LLM backend abstraction
    PERSON_SCHEMA — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.llm import make_backend, LLMBackend
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_backend", "LLMBackend", "PERSON_SCHEMA"]
```

This file doesn't actually change in content — it already imports `make_backend` and `LLMBackend` from `llm.py`. But verify it still works after the llm.py rewrite.

- [ ] **Step 2: Verify imports work**

Run: `.venv/bin/python -c "from src.extraction import make_backend, LLMBackend; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit (only if changes were needed)**

```bash
git add src/extraction/__init__.py
git commit -m "refactor: update extraction package exports for MLX backend"
```

---

### Task 5: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Replace dependencies**

Replace the contents of `requirements.txt` with:

```
Pillow>=10.0
pytest>=8.0
pytesseract>=0.3.10
mlx-lm
mlx-vlm
```

- [ ] **Step 2: Install new dependencies**

Run: `.venv/bin/pip install -r requirements.txt`

Expected: Successful installation of `mlx-lm` and `mlx-vlm` (and their dependencies including `mlx`).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: replace ollama and google-genai with mlx-lm and mlx-vlm"
```

---

### Task 6: Update run.sh

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Rewrite run.sh**

Replace the contents of `run.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Check Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew: brew install python3"
    exit 1
fi

# Check Tesseract is available
if ! command -v tesseract &>/dev/null; then
    echo "Error: tesseract is required but not found."
    echo "Install it with: brew install tesseract"
    exit 1
fi

# Download Dutch language pack if missing
TESSDATA_DIR="$(dirname "$(command -v tesseract)")/../share/tessdata"
if [ ! -f "$TESSDATA_DIR/nld.traineddata" ]; then
    echo "Downloading Dutch language pack for Tesseract..."
    curl -sL -o "$TESSDATA_DIR/nld.traineddata" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/nld.traineddata
    echo "Dutch language pack installed."
    echo ""
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Pre-download MLX models if not cached
echo "Checking MLX models..."
"$VENV_DIR/bin/python" -c "
from mlx_lm import load as lm_load
from mlx_vlm import load as vlm_load
print('  Checking text model...')
lm_load('mlx-community/gemma-3-4b-it-4bit')
print('  Text model ready.')
print('  Checking vision model...')
vlm_load('mlx-community/Qwen2.5-VL-3B-Instruct-4bit')
print('  Vision model ready.')
"
echo ""

# Run the pipeline
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/main.py" "$@"
```

Key changes from the original:
- Removed the `config.json` existence check (lines 32-37 of original)
- Added MLX model pre-download step after venv setup

- [ ] **Step 2: Verify script is executable**

Run: `chmod +x run.sh && head -1 run.sh`

Expected: `#!/usr/bin/env bash`

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "feat: update run.sh to pre-download MLX models, remove config.json requirement"
```

---

### Task 7: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests PASS. If any tests outside `test_llm.py` import `OllamaBackend`, `GeminiBackend`, `GEMINI_MODEL`, or `OLLAMA_MODEL`, they will fail and need updating.

- [ ] **Step 2: Check for stale imports across the codebase**

Run: `grep -rn "OllamaBackend\|GeminiBackend\|GEMINI_MODEL\|OLLAMA_MODEL\|from ollama\|from google.*genai" src/ tests/`

Expected: No results. If any matches are found, update those files to remove the stale references.

- [ ] **Step 3: Verify the app starts**

Run: `.venv/bin/python -c "from src.web import make_server; print('Server module loads OK')"`

Expected: `Server module loads OK`

- [ ] **Step 4: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: clean up stale imports from backend migration"
```
