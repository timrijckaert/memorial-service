# src/extraction/llm.py
"""LLM backend abstraction for the extraction pipeline.

Provides a Protocol (LLMBackend) with two concrete implementations:
  - OllamaBackend  — uses the local ollama server
  - GeminiBackend  — uses the Google Gemini API with 429-retry logic

Use make_backend(config_path) to obtain the correct backend at runtime.
"""

import io
import json
import time
from pathlib import Path
from typing import Optional, Protocol

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from ollama import chat

from src.extraction.schema import GEMINI_MODEL, OLLAMA_MODEL

__all__ = ["LLMBackend", "OllamaBackend", "GeminiBackend", "make_backend"]

_MAX_RETRIES = 3

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
# OllamaBackend
# ---------------------------------------------------------------------------


class OllamaBackend:
    """LLM backend that talks to a local Ollama server."""

    def __init__(self, model: str = OLLAMA_MODEL) -> None:
        self._model = model

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: Optional[dict] = None,
    ) -> str:
        sys = system_prompt
        if json_schema is not None:
            sys = sys + _JSON_INSTRUCTION + json.dumps(json_schema)

        response = chat(
            model=self._model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        text = response.message.content
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
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        response = chat(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [buf.getvalue()],
                }
            ],
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return response.message.content


# ---------------------------------------------------------------------------
# GeminiBackend
# ---------------------------------------------------------------------------


class GeminiBackend:
    """LLM backend that uses the Google Gemini API."""

    def __init__(self, client: genai.Client, model: str = GEMINI_MODEL) -> None:
        self._client = client
        self._model = model

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: Optional[dict] = None,
    ) -> str:
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = json_schema
        config = types.GenerateContentConfig(**config_kwargs)
        response = self._call(model=self._model, contents=user_prompt, config=config)
        return response.text

    def generate_vision(
        self,
        prompt: str,
        image,
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
        """Call Gemini with automatic retry on 429 rate-limit errors."""
        for attempt in range(_MAX_RETRIES):
            try:
                return self._client.models.generate_content(**kwargs)
            except ClientError as e:
                if e.code == 429 and attempt < _MAX_RETRIES - 1:
                    print(f"        Rate limited, waiting 60s...")
                    time.sleep(60)
                else:
                    raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_backend(config_path: Path) -> LLMBackend:
    """Create the appropriate LLM backend from a config file.

    If config_path does not exist, returns OllamaBackend with the default model.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove surrounding markdown code fences from *text*, if present."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
