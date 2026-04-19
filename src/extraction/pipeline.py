# src/extraction/pipeline.py
"""Orchestrates the full extraction pipeline for a single card pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from src.extraction.llm import LLMBackend
from src.extraction.interpretation import interpret_transcription


@dataclass
class ExtractionResult:
    """Result of processing a single card pair through the extraction pipeline."""
    front_name: str
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)


def extract_one(
    front_path: Path,
    back_path: Path | None,
    json_dir: Path,
    backend: LLMBackend | None,
    system_prompt: str | None,
    vision_prompt: str | None,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """Process extraction for a single pair: vision read, then text structuring.

    Pipeline stages (reported via on_step callback):
      1. vision_read   — Vision model reads card images
      2. text_extract  — Text model structures transcription into JSON

    Both stages only run if a backend is provided.
    """
    result = ExtractionResult(front_name=front_path.name)

    if not backend:
        return result

    # Stage 1: Vision read
    if on_step:
        on_step("vision_read")
    try:
        images = [Image.open(front_path)]
        if back_path:
            images.append(Image.open(back_path))

        transcription = backend.generate_vision(
            prompt=vision_prompt,
            images=images,
            temperature=0,
            max_tokens=2048,
        )
    except Exception as e:
        result.errors.append(f"{front_path.name} vision read: {e}")
        return result

    # Stage 2: Text structuring
    if on_step:
        on_step("text_extract")
    json_output_path = json_dir / f"{front_path.stem}.json"
    try:
        interpret_transcription(
            transcription, json_output_path,
            system_prompt, backend,
            front_image_file=front_path.name,
            back_image_file=back_path.name if back_path else None,
        )
        result.interpreted = True
    except Exception as e:
        result.errors.append(f"{front_path.name} interpret: {e}")

    return result
