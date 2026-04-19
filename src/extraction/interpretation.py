# src/extraction/interpretation.py
"""LLM-based structuring of vision transcriptions into biographical data."""

import json
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction.schema import PERSON_SCHEMA
from src.locality import derive_locality


def interpret_transcription(
    transcription: str,
    output_path: Path,
    system_prompt: str,
    backend: LLMBackend,
    front_image_file: str | None = None,
    back_image_file: str | None = None,
) -> None:
    """Structure a vision-model transcription into JSON using the text LLM.

    Sends the system prompt and transcription to the backend with
    json_schema for constrained decoding. Writes the parsed JSON to
    output_path. Raises on failure (caller handles).
    """
    response_text = backend.generate_text(
        system_prompt, transcription,
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
    if front_image_file is not None:
        existing_source["front_image_file"] = front_image_file
    if back_image_file is not None:
        existing_source["back_image_file"] = back_image_file
    existing["source"] = existing_source

    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
