# LLM Backend Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Gemini API with a backend abstraction supporting both Ollama (local, MLX-accelerated) and Gemini (remote API).

**Architecture:** A `LLMBackend` protocol defines `generate_text()` and `generate_vision()`. Two implementations — `OllamaBackend` and `GeminiBackend` — are selected via a `make_backend()` factory that reads `config.json`. The pipeline, worker, and server pass a backend object instead of a Gemini client.

**Tech Stack:** Python 3.12, ollama Python package, google-genai, PIL, pytest

**Spec:** `docs/superpowers/specs/2026-04-07-mlx-local-inference-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/extraction/llm.py` | LLMBackend protocol, OllamaBackend, GeminiBackend, make_backend factory |
| Create | `tests/test_llm.py` | Tests for both backends and factory |
| Modify | `src/extraction/schema.py` | Add OLLAMA_MODEL, keep GEMINI_MODEL |
| Modify | `src/extraction/date_verification.py:18-47` | Replace `client: genai.Client` with `backend: LLMBackend` |
| Modify | `src/extraction/interpretation.py:14-60` | Replace `client: genai.Client` with `backend: LLMBackend`, pass json_schema |
| Modify | `src/extraction/pipeline.py:8,26-99` | Replace `client` param with `backend` |
| Modify | `src/extraction/__init__.py` | Export make_backend, LLMBackend instead of make_gemini_client |
| Modify | `src/web/worker.py:9,54-99` | Replace `client` param with `backend` |
| Modify | `src/web/server.py:10,182-204` | Use make_backend, remove config.json error path |
| Modify | `requirements.txt` | Add ollama, keep google-genai |
| Modify | `tests/test_verify_dates.py` | Mock backend instead of _call_gemini |
| Modify | `tests/test_interpret.py` | Mock backend instead of _call_gemini |
| Modify | `tests/test_pipeline.py` | Replace client with backend in calls |
| Modify | `tests/test_worker.py` | Replace client with backend in calls |
| Delete | `src/extraction/gemini.py` | Replaced by llm.py |
| Delete | `tests/test_gemini.py` | Replaced by test_llm.py |

---

### Task 1: Create LLM backend abstraction with tests

**Files:**
- Create: `src/extraction/llm.py`
- Create: `tests/test_llm.py`
- Modify: `src/extraction/schema.py`

- [ ] **Step 1: Update schema.py with model constants**

In `src/extraction/schema.py`, add the Ollama model constant. Keep GEMINI_MODEL.

```python
# src/extraction/schema.py
"""Shared constants and JSON schema for the extraction pipeline."""

__all__ = ["PERSON_SCHEMA", "GEMINI_MODEL", "OLLAMA_MODEL"]

GEMINI_MODEL = "gemini-2.5-flash"
OLLAMA_MODEL = "gemma3:4b"

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

- [ ] **Step 2: Write tests for OllamaBackend**

Create `tests/test_llm.py`:

```python
# tests/test_llm.py
"""Tests for LLM backend abstraction."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.extraction.llm import (
    OllamaBackend,
    GeminiBackend,
    make_backend,
    _strip_code_fences,
)


# --- OllamaBackend ---

@patch("src.extraction.llm.chat")
def test_ollama_generate_text(mock_chat):
    """OllamaBackend.generate_text calls ollama.chat with correct messages."""
    mock_chat.return_value = MagicMock(message=MagicMock(content="hello"))
    backend = OllamaBackend(model="gemma3:4b")

    result = backend.generate_text("system prompt", "user prompt",
                                   temperature=0, max_tokens=100)

    assert result == "hello"
    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["model"] == "gemma3:4b"
    assert call_kwargs["messages"][0] == {"role": "system", "content": "system prompt"}
    assert call_kwargs["messages"][1] == {"role": "user", "content": "user prompt"}
    assert call_kwargs["options"]["temperature"] == 0
    assert call_kwargs["options"]["num_predict"] == 100


@patch("src.extraction.llm.chat")
def test_ollama_generate_text_with_json_schema(mock_chat):
    """When json_schema is provided, it is appended to system prompt and fences are stripped."""
    mock_chat.return_value = MagicMock(
        message=MagicMock(content='```json\n{"key": "value"}\n```')
    )
    schema = {"type": "object", "properties": {"key": {"type": "string"}}}
    backend = OllamaBackend(model="gemma3:4b")

    result = backend.generate_text("system", "user", temperature=0,
                                   max_tokens=100, json_schema=schema)

    assert result == '{"key": "value"}'
    sys_content = mock_chat.call_args.kwargs["messages"][0]["content"]
    assert "valid JSON" in sys_content
    assert '"key"' in sys_content


@patch("src.extraction.llm.chat")
def test_ollama_generate_vision(mock_chat):
    """OllamaBackend.generate_vision converts PIL image to bytes and sends it."""
    mock_chat.return_value = MagicMock(message=MagicMock(content="1941"))
    backend = OllamaBackend(model="gemma3:4b")
    img = Image.new("RGB", (10, 10), "white")

    result = backend.generate_vision("read this number", img,
                                     temperature=0, max_tokens=16)

    assert result == "1941"
    msg = mock_chat.call_args.kwargs["messages"][0]
    assert msg["content"] == "read this number"
    assert "images" in msg
    assert isinstance(msg["images"][0], bytes)
```

- [ ] **Step 3: Run OllamaBackend tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm.py::test_ollama_generate_text tests/test_llm.py::test_ollama_generate_text_with_json_schema tests/test_llm.py::test_ollama_generate_vision -v`

Expected: FAIL — `ImportError: cannot import name 'OllamaBackend' from 'src.extraction.llm'`

- [ ] **Step 4: Install ollama package**

Run: `.venv/bin/pip install "ollama>=0.4"`

- [ ] **Step 5: Implement OllamaBackend and _strip_code_fences**

Create `src/extraction/llm.py`:

```python
# src/extraction/llm.py
"""LLM backend abstraction with Ollama and Gemini implementations."""

import io
import json
import time
from pathlib import Path
from typing import Protocol

from PIL import Image
from ollama import chat

from src.extraction.schema import GEMINI_MODEL, OLLAMA_MODEL

__all__ = ["LLMBackend", "OllamaBackend", "GeminiBackend", "make_backend"]

_MAX_RETRIES = 3
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY valid JSON matching this schema. "
    "No markdown, no explanation, no code fences.\n"
)


class LLMBackend(Protocol):
    """Protocol for LLM backends used by the extraction pipeline."""

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> str: ...

    def generate_vision(
        self,
        prompt: str,
        image: Image.Image,
        temperature: float,
        max_tokens: int,
    ) -> str: ...


class OllamaBackend:
    """Local inference via Ollama (MLX-accelerated on Apple Silicon)."""

    def __init__(self, model: str = OLLAMA_MODEL):
        self._model = model

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> str:
        sys = system_prompt
        if json_schema:
            sys += _JSON_INSTRUCTION + json.dumps(json_schema, indent=2)
        response = chat(
            model=self._model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        text = response.message.content
        if json_schema:
            text = _strip_code_fences(text)
        return text

    def generate_vision(
        self,
        prompt: str,
        image: Image.Image,
        temperature: float,
        max_tokens: int,
    ) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        response = chat(
            model=self._model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [buf.getvalue()],
            }],
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return response.message.content


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
```

- [ ] **Step 6: Run OllamaBackend tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm.py::test_ollama_generate_text tests/test_llm.py::test_ollama_generate_text_with_json_schema tests/test_llm.py::test_ollama_generate_vision -v`

Expected: 3 passed

- [ ] **Step 7: Write tests for GeminiBackend**

Append to `tests/test_llm.py`:

```python
# --- GeminiBackend ---

def test_gemini_generate_text():
    """GeminiBackend.generate_text calls client.models.generate_content."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text="response")
    backend = GeminiBackend(client=mock_client, model="gemini-2.5-flash")

    result = backend.generate_text("system", "user", temperature=0, max_tokens=100)

    assert result == "response"
    assert mock_client.models.generate_content.call_count == 1


def test_gemini_generate_text_with_json_schema():
    """When json_schema is provided, response_json_schema is set on the config."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text='{"a": 1}')
    backend = GeminiBackend(client=mock_client, model="gemini-2.5-flash")
    schema = {"type": "object"}

    result = backend.generate_text("system", "user", temperature=0,
                                   max_tokens=100, json_schema=schema)

    assert result == '{"a": 1}'
    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema


def test_gemini_generate_vision():
    """GeminiBackend.generate_vision passes the PIL image directly."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text="1941")
    backend = GeminiBackend(client=mock_client, model="gemini-2.5-flash")
    img = Image.new("RGB", (10, 10))

    result = backend.generate_vision("read this", img, temperature=0, max_tokens=16)

    assert result == "1941"
    contents = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert contents == ["read this", img]


def test_gemini_retries_on_429():
    """429 errors trigger retry with 60s wait."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 429
    error.message = "rate limited"
    mock_client.models.generate_content.side_effect = [error, MagicMock(text="ok")]
    backend = GeminiBackend(client=mock_client, model="test")

    with patch("src.extraction.llm.time.sleep") as mock_sleep:
        result = backend.generate_text("sys", "usr", temperature=0, max_tokens=100)

    assert result == "ok"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once_with(60)


def test_gemini_raises_non_429_immediately():
    """Non-429 errors are raised without retry."""
    from google.genai.errors import ClientError

    mock_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.code = 400
    error.message = "bad request"
    mock_client.models.generate_content.side_effect = error
    backend = GeminiBackend(client=mock_client, model="test")

    with pytest.raises(ClientError):
        backend.generate_text("sys", "usr", temperature=0, max_tokens=100)

    assert mock_client.models.generate_content.call_count == 1
```

- [ ] **Step 8: Run GeminiBackend tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm.py::test_gemini_generate_text tests/test_llm.py::test_gemini_retries_on_429 -v`

Expected: FAIL — `ImportError: cannot import name 'GeminiBackend'`

- [ ] **Step 9: Implement GeminiBackend**

Append to `src/extraction/llm.py`, before `_strip_code_fences`:

```python
from google import genai
from google.genai import types
from google.genai.errors import ClientError


class GeminiBackend:
    """Remote inference via Google Gemini API."""

    def __init__(self, client: genai.Client, model: str = GEMINI_MODEL):
        self._client = client
        self._model = model

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> str:
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = json_schema
        config = types.GenerateContentConfig(**config_kwargs)
        response = self._call(model=self._model, contents=user_prompt, config=config)
        return response.text

    def generate_vision(
        self,
        prompt: str,
        image: Image.Image,
        temperature: float,
        max_tokens: int,
    ) -> str:
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = self._call(model=self._model, contents=[prompt, image], config=config)
        return response.text

    def _call(self, **kwargs):
        """Call Gemini with retry on 429 rate limit errors."""
        for attempt in range(_MAX_RETRIES):
            try:
                return self._client.models.generate_content(**kwargs)
            except ClientError as e:
                if e.code == 429 and attempt < _MAX_RETRIES - 1:
                    print(f"        Rate limited, waiting 60s...")
                    time.sleep(60)
                else:
                    raise
```

- [ ] **Step 10: Run GeminiBackend tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm.py -k "gemini" -v`

Expected: 5 passed

- [ ] **Step 11: Write tests for make_backend and _strip_code_fences**

Append to `tests/test_llm.py`:

```python
# --- make_backend ---

def test_make_backend_defaults_to_ollama(tmp_path):
    """When no config.json exists, defaults to OllamaBackend."""
    config_path = tmp_path / "config.json"
    backend = make_backend(config_path)
    assert isinstance(backend, OllamaBackend)
    assert backend._model == "gemma3:4b"


@patch("src.extraction.llm.genai.Client")
def test_make_backend_creates_gemini(mock_client_class, tmp_path):
    """config.json with backend=gemini creates GeminiBackend."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "backend": "gemini",
        "gemini_api_key": "test-key",
    }))

    backend = make_backend(config_path)

    assert isinstance(backend, GeminiBackend)
    mock_client_class.assert_called_once_with(api_key="test-key")


def test_make_backend_creates_ollama_with_custom_model(tmp_path):
    """config.json with backend=ollama and custom model."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "backend": "ollama",
        "ollama_model": "gemma4:e4b",
    }))

    backend = make_backend(config_path)

    assert isinstance(backend, OllamaBackend)
    assert backend._model == "gemma4:e4b"


# --- _strip_code_fences ---

def test_strip_code_fences_removes_json_fences():
    assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_noop_on_plain():
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_strip_code_fences_handles_bare_fences():
    assert _strip_code_fences('```\ntext\n```') == 'text'
```

- [ ] **Step 12: Run make_backend tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm.py -k "make_backend or strip" -v`

Expected: FAIL — `ImportError: cannot import name 'make_backend'`

- [ ] **Step 13: Implement make_backend**

Append to `src/extraction/llm.py`:

```python
def make_backend(config_path: Path) -> LLMBackend:
    """Create an LLM backend from config.json.

    Returns OllamaBackend by default. If config.json exists with
    "backend": "gemini", creates a GeminiBackend with the API key.
    """
    if not config_path.exists():
        return OllamaBackend()
    config = json.loads(config_path.read_text())
    backend_type = config.get("backend", "ollama")
    if backend_type == "gemini":
        client = genai.Client(api_key=config["gemini_api_key"])
        return GeminiBackend(client=client)
    model = config.get("ollama_model", OLLAMA_MODEL)
    return OllamaBackend(model=model)
```

- [ ] **Step 14: Run all test_llm.py tests**

Run: `.venv/bin/python -m pytest tests/test_llm.py -v`

Expected: 14 passed

- [ ] **Step 15: Commit**

```bash
git add src/extraction/llm.py src/extraction/schema.py tests/test_llm.py
git commit -m "feat: add LLM backend abstraction with Ollama and Gemini implementations"
```

---

### Task 2: Update date_verification.py to use LLMBackend

**Files:**
- Modify: `src/extraction/date_verification.py`
- Modify: `tests/test_verify_dates.py`

- [ ] **Step 1: Update tests to use backend mock instead of _call_gemini patch**

Replace the full contents of `tests/test_verify_dates.py`:

```python
# tests/test_verify_dates.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw

from src.extraction.date_verification import verify_dates


def _make_image_with_text(tmp_path: Path, text: str, filename: str = "card.jpeg") -> Path:
    """Create a simple image with text for testing."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), text, fill="black")
    path = tmp_path / filename
    img.save(path, "JPEG")
    return path


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_corrects_misread_year(mock_data, tmp_path):
    """When LLM reads a different year than OCR, the text file is updated."""
    image_path = _make_image_with_text(tmp_path, "overleden 27 Februari 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    backend = MagicMock()
    backend.generate_vision.return_value = "1941"

    mock_data.return_value = {
        "text": ["overleden", "27", "Februari", "1944,"],
        "left": [10, 120, 150, 250],
        "top": [40, 40, 40, 40],
        "width": [100, 20, 80, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 86],
    }

    corrections = verify_dates(image_path, text_path, backend, conflicts_dir)

    assert corrections == ["1944 -> 1941"]
    assert "1941" in text_path.read_text()
    assert "1944" not in text_path.read_text()


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_saves_conflict_image(mock_data, tmp_path):
    """When OCR and LLM disagree, a crop image is saved for manual review."""
    image_path = _make_image_with_text(tmp_path, "1944", filename="card_back.jpeg")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("den 27 Februari 1944")
    conflicts_dir = tmp_path / "conflicts"
    backend = MagicMock()
    backend.generate_vision.return_value = "1941"

    mock_data.return_value = {
        "text": ["1944,"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [86],
    }

    verify_dates(image_path, text_path, backend, conflicts_dir)

    assert conflicts_dir.exists()
    conflict_files = list(conflicts_dir.glob("*.png"))
    assert len(conflict_files) == 1
    assert "ocr1944" in conflict_files[0].name
    assert "llm1941" in conflict_files[0].name


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_correction_when_matching(mock_data, tmp_path):
    """When LLM and OCR agree, text is unchanged."""
    image_path = _make_image_with_text(tmp_path, "geboren 15 Juni 1852")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("geboren 15 Juni 1852")
    backend = MagicMock()
    backend.generate_vision.return_value = "1852"

    mock_data.return_value = {
        "text": ["geboren", "15", "Juni", "1852"],
        "left": [10, 100, 130, 200],
        "top": [40, 40, 40, 40],
        "width": [80, 20, 40, 50],
        "height": [20, 20, 20, 20],
        "conf": [95, 96, 95, 68],
    }

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "geboren 15 Juni 1852"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_rejects_llm_year_outside_range(mock_data, tmp_path):
    """When LLM returns a year outside 1800-1950, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1926")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1926")
    backend = MagicMock()
    backend.generate_vision.return_value = "2026"

    mock_data.return_value = {
        "text": ["overleden", "1926"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "overleden 1926"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_years_skips_llm(mock_data, tmp_path):
    """When no year-like words are found, no LLM calls are made."""
    image_path = _make_image_with_text(tmp_path, "no dates here")
    text_path = tmp_path / "card_front.txt"
    text_path.write_text("no dates here")
    backend = MagicMock()

    mock_data.return_value = {
        "text": ["no", "dates", "here"],
        "left": [10, 30, 70],
        "top": [40, 40, 40],
        "width": [15, 35, 30],
        "height": [20, 20, 20],
        "conf": [95, 95, 95],
    }

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    backend.generate_vision.assert_not_called()


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_ignores_invalid_llm_response(mock_data, tmp_path):
    """When LLM returns non-year text, the OCR value is kept."""
    image_path = _make_image_with_text(tmp_path, "overleden 1944")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("overleden 1944")
    backend = MagicMock()
    backend.generate_vision.return_value = "The year shown is 1941"

    mock_data.return_value = {
        "text": ["overleden", "1944"],
        "left": [10, 120],
        "top": [40, 40],
        "width": [100, 50],
        "height": [20, 20],
        "conf": [95, 86],
    }

    corrections = verify_dates(image_path, text_path, backend)

    assert corrections == []
    assert text_path.read_text() == "overleden 1944"


@patch("src.extraction.date_verification.pytesseract.image_to_data")
def test_verify_dates_no_stray_crop_files(mock_data, tmp_path):
    """No stray crop files are left after verification."""
    image_path = _make_image_with_text(tmp_path, "1913")
    text_path = tmp_path / "card_back.txt"
    text_path.write_text("1913")
    backend = MagicMock()
    backend.generate_vision.return_value = "1913"

    mock_data.return_value = {
        "text": ["1913"],
        "left": [10],
        "top": [40],
        "width": [50],
        "height": [20],
        "conf": [95],
    }

    verify_dates(image_path, text_path, backend)

    crop_files = list(tmp_path.glob("_crop_*.png"))
    assert crop_files == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_verify_dates.py -v`

Expected: FAIL — `verify_dates()` still expects `client: genai.Client`

- [ ] **Step 3: Update date_verification.py implementation**

Replace full contents of `src/extraction/date_verification.py`:

```python
# src/extraction/date_verification.py
"""Verify OCR-read year digits by visual cross-check with an LLM."""

import re
from pathlib import Path

from PIL import Image
import pytesseract

from src.extraction.llm import LLMBackend

_YEAR_RE = re.compile(r"^\d{4}$")


def verify_dates(
    image_path: Path,
    text_path: Path,
    backend: LLMBackend,
    conflicts_dir: Path | None = None,
) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking the LLM.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to the LLM for visual verification.
    If the LLM reads a different year, the text file is updated in place and
    the crop image is saved to conflicts_dir for manual review.

    Returns a list of corrections made (empty if all years match).
    """
    image = Image.open(image_path)
    data = pytesseract.image_to_data(
        image, lang="nld", output_type=pytesseract.Output.DICT
    )

    years = _find_year_regions(data)
    if not years:
        return []

    corrections = []
    text = text_path.read_text()

    for entry in years:
        crop = _crop_year_region(image, entry)
        llm_year = _ask_llm_for_year(backend, crop)
        if llm_year is None:
            continue

        if _should_correct(entry["ocr_year"], llm_year):
            text = text.replace(entry["ocr_year"], llm_year, 1)
            corrections.append(f"{entry['ocr_year']} -> {llm_year}")

            if conflicts_dir:
                _save_conflict_crop(conflicts_dir, image_path.stem, entry["ocr_year"], llm_year, crop)

    if corrections:
        text_path.write_text(text)

    return corrections


def _find_year_regions(data: dict) -> list[dict]:
    """Find 4-digit year-like words in Tesseract bounding-box data."""
    years = []
    for i, word in enumerate(data["text"]):
        clean_word = word.strip().rstrip(",.")
        if _YEAR_RE.match(clean_word):
            years.append({
                "ocr_year": clean_word,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            })
    return years


def _crop_year_region(image: Image.Image, entry: dict, pad: int = 10) -> Image.Image:
    """Crop an image region around a detected year word."""
    return image.crop((
        max(0, entry["left"] - pad),
        max(0, entry["top"] - pad),
        entry["left"] + entry["width"] + pad,
        entry["top"] + entry["height"] + pad,
    ))


def _ask_llm_for_year(backend: LLMBackend, crop: Image.Image) -> str | None:
    """Send a cropped year image to the LLM and return the read year, or None."""
    text = backend.generate_vision(
        "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
        crop,
        temperature=0,
        max_tokens=16,
    )
    if not text:
        return None
    cleaned = text.strip().rstrip(",.")
    return cleaned if _YEAR_RE.match(cleaned) else None


def _should_correct(ocr_year: str, llm_year: str) -> bool:
    """Check if the LLM year is different from OCR and within valid range (1800-1950)."""
    return llm_year != ocr_year and 1800 <= int(llm_year) <= 1950


def _save_conflict_crop(
    conflicts_dir: Path, stem: str, ocr_year: str, llm_year: str, crop: Image.Image
) -> None:
    """Save a conflict crop image for manual review."""
    conflicts_dir.mkdir(exist_ok=True)
    conflict_path = conflicts_dir / f"{stem}_ocr{ocr_year}_llm{llm_year}.png"
    crop.save(conflict_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_verify_dates.py -v`

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/extraction/date_verification.py tests/test_verify_dates.py
git commit -m "refactor: update date_verification to use LLMBackend"
```

---

### Task 3: Update interpretation.py to use LLMBackend

**Files:**
- Modify: `src/extraction/interpretation.py`
- Modify: `tests/test_interpret.py`

- [ ] **Step 1: Update tests to use backend mock**

Replace full contents of `tests/test_interpret.py`:

```python
# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import MagicMock

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

    call_args = backend.generate_text.call_args
    user_message = call_args.args[1]
    assert "Voorkant tekst" in user_message
    assert "Achterkant tekst" in user_message
    assert "{front_text}" not in user_message
    assert "{back_text}" not in user_message


def test_interpret_text_passes_json_schema(tmp_path):
    """generate_text is called with json_schema=PERSON_SCHEMA."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, SYSTEM_PROMPT, USER_TEMPLATE, backend)

    call_kwargs = backend.generate_text.call_args.kwargs
    assert "json_schema" in call_kwargs
    assert call_kwargs["json_schema"]["required"] == ["person", "notes"]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_interpret.py -v`

Expected: FAIL — `interpret_text()` still expects `client: genai.Client`

- [ ] **Step 3: Update interpretation.py implementation**

Replace full contents of `src/extraction/interpretation.py`:

```python
# src/extraction/interpretation.py
"""LLM-based interpretation of OCR text into structured biographical data."""

import json
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction.schema import PERSON_SCHEMA


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
    backend: LLMBackend,
) -> None:
    """Interpret OCR text using the LLM backend and write structured JSON.

    Sends the static system prompt and card-specific user message to the
    backend with structured JSON output. Writes the parsed JSON to output_path.
    Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    user_message = user_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response_text = backend.generate_text(
        system_prompt, user_message,
        temperature=0, max_tokens=2048,
        json_schema=PERSON_SCHEMA,
    )

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response_text[:200]}"
        ) from e

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_interpret.py -v`

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/extraction/interpretation.py tests/test_interpret.py
git commit -m "refactor: update interpretation to use LLMBackend"
```

---

### Task 4: Update pipeline.py to use LLMBackend

**Files:**
- Modify: `src/extraction/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Update tests to replace client with backend**

Replace full contents of `tests/test_pipeline.py`:

```python
# tests/test_pipeline.py
"""Tests for the extraction pipeline orchestration."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.extraction.pipeline import extract_one, ExtractionResult


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_calls_steps_in_order(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Pipeline calls OCR, date verify, and interpret in order."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_backend = MagicMock()
    mock_verify.return_value = []

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_backend, "system", "template",
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back", "date_verify", "llm_extract"]
    assert mock_ocr.call_count == 2
    assert mock_verify.call_count == 2
    assert mock_interpret.call_count == 1
    assert result.ocr_done is True
    assert result.interpreted is True
    assert result.errors == []


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_stops_on_ocr_front_failure(mock_ocr, tmp_path):
    """If OCR front fails, the pipeline stops and reports the error."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_ocr.side_effect = RuntimeError("tesseract crashed")

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
    )

    assert result.ocr_done is False
    assert len(result.errors) == 1
    assert "OCR front" in result.errors[0]


@patch("src.extraction.pipeline.extract_text")
def test_extract_one_skips_llm_without_backend(mock_ocr, tmp_path):
    """Without a backend, date verify and interpret are skipped."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"

    steps = []
    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        None, None, None,
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["ocr_front", "ocr_back"]
    assert result.ocr_done is True
    assert result.interpreted is False


@patch("src.extraction.pipeline.interpret_text")
@patch("src.extraction.pipeline.verify_dates")
@patch("src.extraction.pipeline.extract_text")
def test_extract_one_reports_date_corrections(mock_ocr, mock_verify, mock_interpret, tmp_path):
    """Date corrections are counted and recorded."""
    front = tmp_path / "card.jpeg"
    back = tmp_path / "card 1.jpeg"
    front.touch()
    back.touch()
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    conflicts_dir = tmp_path / "conflicts"
    mock_backend = MagicMock()
    mock_verify.side_effect = [["1944 -> 1941"], []]

    result = extract_one(
        front, back, text_dir, json_dir, conflicts_dir,
        mock_backend, "system", "template",
    )

    assert result.verify_corrections == 1
    assert len(result.date_fixes) == 1


def test_extraction_result_defaults():
    """ExtractionResult has sensible defaults."""
    result = ExtractionResult(front_name="test.jpeg")

    assert result.front_name == "test.jpeg"
    assert result.ocr_done is False
    assert result.verify_corrections == 0
    assert result.interpreted is False
    assert result.errors == []
    assert result.date_fixes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`

Expected: FAIL — `extract_one()` still imports `genai.Client`

- [ ] **Step 3: Update pipeline.py implementation**

Replace full contents of `src/extraction/pipeline.py`:

```python
# src/extraction/pipeline.py
"""Orchestrates the full extraction pipeline for a single card pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.extraction.llm import LLMBackend
from src.extraction.ocr import extract_text
from src.extraction.date_verification import verify_dates
from src.extraction.interpretation import interpret_text


@dataclass
class ExtractionResult:
    """Result of processing a single card pair through the extraction pipeline."""
    front_name: str
    ocr_done: bool = False
    verify_corrections: int = 0
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)
    date_fixes: list[str] = field(default_factory=list)


def extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    backend: LLMBackend | None,
    system_prompt: str | None,
    user_template: str | None,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """Process extraction for a single pair: OCR, date verification, LLM interpretation.

    Pipeline stages (reported via on_step callback):
      1. ocr_front   — Tesseract OCR on front image
      2. ocr_back    — Tesseract OCR on back image
      3. date_verify — LLM visual cross-check of year digits
      4. llm_extract — LLM structured data extraction

    Stages 3-4 only run if a backend is provided.
    """
    result = ExtractionResult(front_name=front_path.name)

    front_text_path = text_dir / f"{front_path.stem}_front.txt"
    back_text_path = text_dir / f"{back_path.stem}_back.txt"

    # OCR Front
    if on_step:
        on_step("ocr_front")
    try:
        extract_text(front_path, front_text_path)
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR front: {e}")
        return result

    # OCR Back
    if on_step:
        on_step("ocr_back")
    try:
        extract_text(back_path, back_text_path)
        result.ocr_done = True
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR back: {e}")
        return result

    # Date verification (LLM visual cross-check)
    if backend:
        if on_step:
            on_step("date_verify")
        try:
            for txt_path, img_path in [
                (front_text_path, front_path),
                (back_text_path, back_path),
            ]:
                corrections = verify_dates(img_path, txt_path, backend, conflicts_dir)
                for c in corrections:
                    result.verify_corrections += 1
                    result.date_fixes.append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result.errors.append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if backend:
        if on_step:
            on_step("llm_extract")
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(
                front_text_path, back_text_path, json_output_path,
                system_prompt, user_template, backend,
            )
            result.interpreted = True
        except Exception as e:
            result.errors.append(f"{front_path.name} interpret: {e}")

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/extraction/pipeline.py tests/test_pipeline.py
git commit -m "refactor: update pipeline to use LLMBackend"
```

---

### Task 5: Update worker, server, and __init__ to use LLMBackend

**Files:**
- Modify: `src/web/worker.py`
- Modify: `src/web/server.py`
- Modify: `src/extraction/__init__.py`
- Modify: `tests/test_worker.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Update worker.py**

Replace full contents of `src/web/worker.py`:

```python
# src/web/worker.py
"""Background extraction worker thread."""

import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction import extract_one


@dataclass
class CardError:
    """An error that occurred during extraction of a single card."""
    card_id: str
    reason: str


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    current: dict | None = None
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)


class ExtractionWorker:
    """Runs extraction sequentially on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._status = ExtractionStatus(status="idle")

    def get_status(self) -> ExtractionStatus:
        """Return a snapshot copy of the current status."""
        with self._lock:
            return ExtractionStatus(
                status=self._status.status,
                current=dict(self._status.current) if self._status.current else None,
                done=list(self._status.done),
                errors=[CardError(e.card_id, e.reason) for e in self._status.errors],
                queue=list(self._status.queue),
            )

    def start(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ) -> bool:
        """Start extraction on a background thread. Returns False if already running."""
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._status = ExtractionStatus(
                status="running",
                queue=queue_names,
            )
            self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        """Signal the worker to stop after the current card."""
        self._cancel.set()
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"

    def _run(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ):
        """Process all pairs sequentially. Runs on a background thread."""
        for front_path, back_path in pairs:
            if self._cancel.is_set():
                with self._lock:
                    self._status.status = "cancelled"
                return

            card_name = front_path.stem

            with self._lock:
                if card_name in self._status.queue:
                    self._status.queue.remove(card_name)
                self._status.current = {"card_id": card_name, "step": "ocr_front"}

            def _on_step(step):
                with self._lock:
                    if self._status.current:
                        self._status.current["step"] = step

            result = extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                backend, system_prompt, user_template,
                on_step=_on_step,
            )

            with self._lock:
                if result.errors:
                    self._status.errors.append(
                        CardError(card_id=card_name, reason="; ".join(result.errors))
                    )
                else:
                    self._status.done.append(card_name)
                self._status.current = None

        with self._lock:
            if self._status.status != "cancelled":
                self._status.status = "idle"
```

- [ ] **Step 2: Update tests/test_worker.py**

The worker tests pass `None` as the last argument to `worker.start()`. The parameter name changed from `client` to `backend`, but since it's positional, the tests still work. Verify:

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`

Expected: 5 passed (no test changes needed — all tests pass `None` positionally)

- [ ] **Step 3: Update server.py**

Replace full contents of `src/web/server.py`:

```python
# src/web/server.py
"""HTTP server for the memorial card web application."""

import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from src.extraction import make_backend
from src.images import find_pairs, merge_all
from src.review import list_cards, load_card, save_card
from src.web.worker import ExtractionWorker

_STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppHandler(BaseHTTPRequestHandler):
    """HTTP handler for the memorial card web app."""

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _serve_file(self, base_dir: Path, filename: str):
        """Serve a file from base_dir with path traversal protection."""
        file_path = (base_dir / filename).resolve()
        if not str(file_path).startswith(str(base_dir.resolve())):
            self._send_error(403, "Forbidden")
            return
        if not file_path.exists():
            self._send_error(404, "Not found")
            return

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        json_dir = self.server.json_dir
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir

        if self.path == "/":
            self._serve_file(_STATIC_DIR, "index.html")
        elif self.path.startswith("/static/"):
            filename = unquote(self.path[len("/static/"):])
            self._serve_file(_STATIC_DIR, filename)
        elif self.path == "/api/cards":
            self._send_json(list_cards(json_dir))
        elif self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            result = load_card(card_id, json_dir, input_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                self._send_json(result)
        elif self.path.startswith("/images/"):
            filename = unquote(self.path[len("/images/"):])
            self._serve_file(input_dir, filename)
        elif self.path.startswith("/output-images/"):
            filename = unquote(self.path[len("/output-images/"):])
            self._serve_file(output_dir, filename)
        elif self.path == "/api/merge/pairs":
            pairs, errors = find_pairs(input_dir)
            result = {
                "pairs": [
                    {
                        "name": front.stem,
                        "front": front.name,
                        "back": back.name,
                        "merged": (output_dir / front.name).exists(),
                    }
                    for front, back in pairs
                ],
                "errors": errors,
            }
            self._send_json(result)
        elif self.path == "/api/extract/status":
            self._send_json(self.server.worker.get_status().to_dict())
        elif self.path == "/api/extract/cards":
            pairs, _ = find_pairs(input_dir)
            cards = []
            for front, back in pairs:
                has_json = (json_dir / f"{front.stem}.json").exists()
                cards.append({
                    "name": front.stem,
                    "front": front.name,
                    "back": back.name,
                    "status": "done" if has_json else "pending",
                })
            self._send_json({"cards": cards})
        else:
            self._send_error(404, "Not found")

    def do_PUT(self):
        json_dir = self.server.json_dir

        if self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                updated_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return

            json_path = json_dir / f"{card_id}.json"
            if not json_path.exists():
                self._send_error(404, "Card not found")
                return

            save_card(card_id, json_dir, updated_data)
            self._send_json({"status": "saved"})
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir
        json_dir = self.server.json_dir

        if self.path == "/api/merge":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            pairs, pairing_errors = find_pairs(input_dir)
            ok_count, skipped, merge_errors = merge_all(pairs, output_dir, force=force)
            self._send_json({
                "ok": ok_count,
                "skipped": skipped,
                "errors": pairing_errors + merge_errors,
            })
        elif self.path == "/api/extract":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            cards_filter = options.get("cards", None)
            pairs, _ = find_pairs(input_dir)
            if cards_filter:
                card_set = set(cards_filter)
                pairs = [(f, b) for f, b in pairs if f.stem in card_set]
            text_dir = output_dir / "text"
            text_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)
            conflicts_dir = output_dir / "date_conflicts"

            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            user_template_path = prompts_dir / "extract_person_user.txt"
            system_prompt = None
            user_template = None
            if system_prompt_path.exists() and user_template_path.exists():
                system_prompt = system_prompt_path.read_text()
                user_template = user_template_path.read_text()

            backend = self.server.backend if system_prompt else None

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, backend,
            )
            if started:
                self._send_json({"status": "started"})
            else:
                self._send_json({"status": "already_running"}, 409)
        elif self.path == "/api/extract/cancel":
            self.server.worker.cancel()
            self._send_json({"status": "cancelling"})
        else:
            self._send_error(404, "Not found")


def make_server(
    json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0
) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    server.worker = ExtractionWorker()
    config_path = input_dir.parent / "config.json"
    server.backend = make_backend(config_path)
    return server
```

- [ ] **Step 4: Update __init__.py**

Replace full contents of `src/extraction/__init__.py`:

```python
# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one    — Run the full 4-step pipeline for one card pair
    make_backend   — Create an LLM backend from config
    LLMBackend     — Protocol for LLM backends
    PERSON_SCHEMA  — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.llm import make_backend, LLMBackend
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_backend", "LLMBackend", "PERSON_SCHEMA"]
```

- [ ] **Step 5: Run worker and server tests**

Run: `.venv/bin/python -m pytest tests/test_worker.py tests/test_server.py -v`

Expected: All tests pass. Server tests work because `make_backend` defaults to `OllamaBackend` (no config.json in tmp_path), and `extract_one` is mocked in integration tests.

- [ ] **Step 6: Commit**

```bash
git add src/web/worker.py src/web/server.py src/extraction/__init__.py
git commit -m "refactor: update worker, server, and exports to use LLMBackend"
```

---

### Task 6: Clean up old files, update requirements, final test run

**Files:**
- Delete: `src/extraction/gemini.py`
- Delete: `tests/test_gemini.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Delete old gemini module and its tests**

```bash
git rm src/extraction/gemini.py tests/test_gemini.py
```

- [ ] **Step 2: Update requirements.txt**

Replace full contents of `requirements.txt`:

```
Pillow>=10.0
pytest>=8.0
pytesseract>=0.3.10
google-genai>=1.0
ollama>=0.4
```

- [ ] **Step 3: Install new dependency**

Run: `.venv/bin/pip install -r requirements.txt`

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests pass. No test imports `gemini.py` or `_call_gemini`.

- [ ] **Step 5: Verify no stale imports remain**

Run: `grep -r "from src.extraction.gemini" src/ tests/` and `grep -r "_call_gemini" src/ tests/` and `grep -r "make_gemini_client" src/ tests/`

Expected: No matches found.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove gemini.py, add ollama dependency"
```
