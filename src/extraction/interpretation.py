# src/extraction/interpretation.py
"""LLM-based interpretation of OCR text into structured biographical data."""

import json
from pathlib import Path

from google import genai
from google.genai import types

from src.extraction.gemini import _call_gemini
from src.extraction.schema import GEMINI_MODEL, PERSON_SCHEMA


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
    client: genai.Client,
) -> None:
    """Interpret OCR text using Gemini and write structured JSON.

    Sends the static system prompt and card-specific user message to Gemini
    with structured JSON output. Writes the parsed JSON to output_path.
    Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    user_message = user_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response = _call_gemini(
        client,
        model=GEMINI_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_json_schema=PERSON_SCHEMA,
        ),
    )

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response.text[:200]}"
        ) from e

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
