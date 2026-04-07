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
    """Interpret OCR text using an LLM backend and write structured JSON.

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
