# LLM Backend Abstraction — Design Spec

**Date:** 2026-04-07
**Status:** Draft

## Problem

The extraction pipeline is hardcoded to the Gemini API (gemini-2.5-flash, free tier) for date verification (vision) and text interpretation (structured JSON). The free tier limits (10 RPM, 250 RPD) make it impossible to process a full batch without interruption. We want to add Ollama as a local alternative while keeping Gemini as an option.

## Decision

Introduce a backend abstraction that the pipeline calls. Two implementations: `OllamaBackend` (local, MLX-accelerated) and `GeminiBackend` (remote API). The active backend is selected at startup via configuration.

## Backends

### Ollama (local)
- Uses `gemma3:4b` (already downloaded, 3.3GB, vision-capable).
- MLX-accelerated since Ollama 0.19+ — significantly faster than the old llama.cpp backend.
- No rate limits, no API key, no cost.
- Requires Ollama running locally.
- `gemma4:e4b` available as an upgrade path.

### Gemini (remote)
- Uses `gemini-2.5-flash` (current setup).
- Free tier: 10 RPM, 250 RPD.
- Requires `config.json` with API key.
- Keeps existing retry-on-429 logic.

## Architecture

### `src/extraction/llm.py` — Backend abstraction

Replaces `src/extraction/gemini.py`. Defines a simple `LLMBackend` protocol and two implementations.

```python
from typing import Protocol

class LLMBackend(Protocol):
    def generate_text(self, system_prompt: str, user_prompt: str,
                      temperature: float, max_tokens: int) -> str: ...

    def generate_vision(self, prompt: str, image: Image.Image,
                        temperature: float, max_tokens: int) -> str: ...
```

**`OllamaBackend`**
- Constructed with a model name (default `gemma3:4b`).
- `generate_text()` — calls `ollama.chat()` with system + user messages.
- `generate_vision()` — converts PIL Image to PNG bytes, calls `ollama.chat()` with `images` parameter.

**`GeminiBackend`**
- Constructed with a `genai.Client` (from config.json API key).
- `generate_text()` — calls `client.models.generate_content()` with text. Keeps retry-on-429 logic.
- `generate_vision()` — calls `client.models.generate_content()` with image. Keeps retry-on-429 logic.
- Gemini's `response_json_schema` is used here since the API supports it natively.

**`make_backend(config_path: Path) -> LLMBackend`**
- Factory function. Reads `config.json`.
- If `"backend": "gemini"` and a `gemini_api_key` is present → `GeminiBackend`.
- If `"backend": "ollama"` (or no config.json exists) → `OllamaBackend`.
- Ollama is the default when no config exists.

### Changes to existing modules

**`src/extraction/schema.py`**
- Remove `GEMINI_MODEL` constant.
- Add `OLLAMA_MODEL = "gemma3:4b"` and `GEMINI_MODEL = "gemini-2.5-flash"` (each backend uses its own).
- `PERSON_SCHEMA` stays as-is.

**`src/extraction/date_verification.py`**
- Replace `_call_gemini` with `backend.generate_vision()`.
- `verify_dates()` signature: replace `client: genai.Client` with `backend: LLMBackend`.

**`src/extraction/interpretation.py`**
- Replace `_call_gemini` with `backend.generate_text()`.
- For the Ollama path: no native JSON schema enforcement, so embed the schema in the prompt and strip markdown fences before parsing.
- For the Gemini path: `GeminiBackend.generate_text()` handles JSON schema internally and returns clean JSON.
- `interpret_text()` signature: replace `client: genai.Client` with `backend: LLMBackend`.

**`src/extraction/pipeline.py`**
- Replace `client: genai.Client | None` with `backend: LLMBackend | None`.
- Keep `if backend:` guards (user may still want OCR-only mode).

**`src/extraction/__init__.py`**
- Export `make_backend` and `LLMBackend` instead of `make_gemini_client`.

**`src/web/worker.py`**
- Replace `client: genai.Client | None` with `backend: LLMBackend | None` in `start()` and `_run()`.

**`src/web/server.py`**
- Call `make_backend()` instead of `make_gemini_client()`. Store on the server object.
- Falls back to Ollama if no config.json — no more error when config is missing.

**`requirements.txt`**
- Keep `google-genai>=1.0`.
- Add `ollama>=0.4`.

### Files to delete

- `src/extraction/gemini.py` — logic moves into `GeminiBackend` within `llm.py`.

### Files unchanged

- `src/extraction/ocr.py` — no LLM involvement.
- `src/web/static/*` — frontend is backend-agnostic.
- `prompts/*` — system/user prompts stay the same.

## JSON Output Strategy

**Gemini backend:** Uses `response_json_schema` and `response_mime_type="application/json"` as today. Returns clean JSON.

**Ollama backend:** No native schema enforcement. The `generate_text()` method in `OllamaBackend`:
1. Appends the JSON schema to the system prompt with the instruction: "Respond with ONLY valid JSON matching this schema. No markdown, no explanation."
2. Strips markdown code fences from the response before returning.
3. Callers (`interpret_text`) parse with `json.loads()` as before.

## config.json Format

```json
{
  "backend": "ollama",
  "ollama_model": "gemma3:4b"
}
```

Or for Gemini:

```json
{
  "backend": "gemini",
  "gemini_api_key": "AIza..."
}
```

If no config.json exists, defaults to Ollama with `gemma3:4b`.

## Testing

- `test_gemini.py` → rename to `test_llm.py`.
- Test both backend implementations with mocks.
- Integration-level tests in `test_pipeline.py` / `test_interpret.py` / `test_verify_dates.py` mock at the `LLMBackend` level.
