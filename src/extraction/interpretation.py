# src/extraction/interpretation.py
"""LLM-based interpretation of OCR text into structured biographical data."""

import json
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction.schema import PERSON_SCHEMA
from src.locality import derive_locality


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
    backend: LLMBackend,
    front_image_file: str | None = None,
    back_image_file: str | None = None,
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

    # Title-case names — LLM sometimes passes through ALL-CAPS from the card
    person = result.get("person", {})
    for field in ("first_name", "last_name"):
        if isinstance(person.get(field), str):
            person[field] = person[field].title()
    if isinstance(person.get("spouses"), list):
        person["spouses"] = [
            s.title() if isinstance(s, str) else s for s in person["spouses"]
        ]

    # Derive locality for filename
    person["locality"] = derive_locality(result)

    # Read existing file (skeleton from match phase) if present
    existing = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text())

    # Merge extracted data into existing structure
    existing["person"] = result.get("person", {})
    existing["notes"] = result.get("notes", [])
    existing_source = existing.get("source", {})
    existing_source["front_text_file"] = front_text_path.name
    existing_source["back_text_file"] = back_text_path.name
    if front_image_file is not None:
        existing_source["front_image_file"] = front_image_file
    if back_image_file is not None:
        existing_source["back_image_file"] = back_image_file
    existing["source"] = existing_source

    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
