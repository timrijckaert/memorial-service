# src/extraction/llm.py
"""LLM backend abstraction for the extraction pipeline.

Provides a Protocol (LLMBackend) and a single concrete implementation:
  - MLXBackend — runs models in-process via Apple's MLX framework

Use make_backend(config_path) to obtain the backend at runtime.
"""

import json
import os
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

        try:
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
        finally:
            os.unlink(image_path)


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
