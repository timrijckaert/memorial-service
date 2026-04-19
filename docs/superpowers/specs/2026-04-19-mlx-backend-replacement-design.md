# MLX Backend Replacement — Design Spec

**Date:** 2026-04-19
**Status:** Draft

## Problem

The extraction pipeline currently supports two LLM backends: Ollama (local server) and Gemini (cloud API). Both have drawbacks:

- **Ollama** requires installing and running a separate server process
- **Gemini** requires an API key and has rate limits (10 RPM, 250 RPD on free tier)
- Neither is pip-installable — both add setup friction for distribution

The target machine is a MacBook Air M3 with 16GB RAM.

## Decision

Replace both backends with a single **MLX backend** using Apple's MLX framework. MLX runs models directly in-process via pip-installable Python packages, with native Metal acceleration on Apple Silicon. No external server, no API key, no rate limits.

Ollama and Gemini backends are removed entirely.

## Models

Two models, lazy-loaded on first use:

| Task | Model | Size | Library |
|------|-------|------|---------|
| Text interpretation | `mlx-community/gemma-3-4b-it-4bit` | ~2.5GB | `mlx-lm` |
| Date verification (vision) | `mlx-community/Qwen2.5-VL-3B-Instruct-4bit` | ~2GB | `mlx-vlm` |

**Memory budget (16GB MacBook Air M3):**

| | Size |
|---|---|
| Text model | ~2.5GB |
| Vision model | ~2.0GB |
| macOS + apps | ~6-8GB |
| Headroom | ~4-5GB |

**Why not Gemma 4?** Gemma 4 is natively multimodal (single model for both tasks), but the current mlx-community quantizations have a [PLE quantization bug](https://huggingface.co/mlx-community/gemma-4-e2b-4bit/discussions/1) that produces garbage output. A [fixed repo](https://github.com/FakeRocket543/mlx-gemma4) exists but produces much larger model files (7.6-10.3GB). Once this is fixed upstream, switching to a single Gemma 4 model is a config change.

**Model caching:** HuggingFace hub stores downloaded models in `~/.cache/huggingface/`. First download happens during `run.sh` bootstrap (see below). Subsequent runs use the cache.

## Architecture

### `src/extraction/llm.py` — Rewritten

The file is simplified to:

- `LLMBackend` protocol (unchanged — still useful for test mocks)
- `MLXBackend` class (new — the only real implementation)
- `make_backend()` factory (simplified — just returns `MLXBackend()`)
- `_strip_code_fences()` helper (kept — MLX has no native JSON schema enforcement)
- `_JSON_INSTRUCTION` constant (kept — embedded in prompts for JSON output)

```python
class MLXBackend:
    def __init__(
        self,
        text_model: str = MLX_TEXT_MODEL,
        vision_model: str = MLX_VISION_MODEL,
    ) -> None:
        self._text_model_name = text_model
        self._vision_model_name = vision_model
        self._text_model = None      # lazy-loaded
        self._text_tokenizer = None
        self._vision_model = None    # lazy-loaded
        self._vision_processor = None

    def generate_text(self, system_prompt, user_prompt, temperature, max_tokens, json_schema=None) -> str:
        # Lazy-load text model on first call
        # Combine system_prompt + user_prompt into chat format
        # Append JSON schema instruction if json_schema is provided
        # Call mlx_lm.generate()
        # Strip code fences if json_schema was provided
        ...

    def generate_vision(self, prompt, image, temperature, max_tokens) -> str:
        # Lazy-load vision model on first call
        # Call mlx_vlm.generate() with image
        ...
```

### Deleted code

| What | Why |
|------|-----|
| `OllamaBackend` class | Replaced by MLXBackend |
| `GeminiBackend` class | Replaced by MLXBackend |
| `from ollama import chat` | No longer needed |
| `from google import genai` | No longer needed |
| Gemini retry-on-429 logic | No rate limits with local inference |

### `src/extraction/schema.py` — Constants updated

```python
MLX_TEXT_MODEL = "mlx-community/gemma-3-4b-it-4bit"
MLX_VISION_MODEL = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
```

`GEMINI_MODEL` and `OLLAMA_MODEL` are removed.

### `requirements.txt` — Dependencies swapped

**Remove:**
- `google-genai>=1.0`
- `ollama>=0.4`

**Add:**
- `mlx-lm`
- `mlx-vlm`

### `run.sh` — Updated bootstrap

1. Remove the `config.json` existence check (no longer needed)
2. Add model pre-download step after venv setup:

```bash
# Pre-download MLX models if not cached
echo "Checking MLX models..."
"$VENV_DIR/bin/python" -c "
from mlx_lm import load
from mlx_vlm import load as vlm_load
print('  Checking text model...')
load('mlx-community/gemma-3-4b-it-4bit')
print('  Text model ready.')
print('  Checking vision model...')
vlm_load('mlx-community/Qwen2.5-VL-3B-Instruct-4bit')
print('  Vision model ready.')
"
```

### `config.json` — Optional

No longer required. If present with model overrides, they're used:

```json
{
  "mlx_text_model": "mlx-community/some-other-model",
  "mlx_vision_model": "mlx-community/some-other-vision-model"
}
```

If absent, defaults from `schema.py` are used. No API keys, no backend selection.

### Files unchanged

- `src/extraction/interpretation.py` — calls `backend.generate_text()`, backend-agnostic
- `src/extraction/date_verification.py` — calls `backend.generate_vision()`, backend-agnostic
- `src/extraction/pipeline.py` — receives backend, passes it through
- `src/extraction/ocr.py` — no LLM involvement
- `src/web/worker.py` — receives backend, passes it through
- `src/web/server.py` — calls `make_backend()`, stores result (unchanged usage)
- Frontend — backend-agnostic

## Testing

- `tests/test_llm.py` — rewrite to test `MLXBackend` with mocks
- Remove any Gemini/Ollama-specific test fixtures
- Integration tests continue to mock at the `LLMBackend` protocol level (unchanged)

## Future Work

- **OCR removal:** If the vision model proves capable enough, the entire OCR stage (Tesseract) could be replaced by sending raw card images directly to the LLM. Separate design.
- **Gemma 4 upgrade:** Once the PLE quantization bug is fixed in mlx-community, switch to a single Gemma 4 multimodal model for both text and vision. Config-only change.
