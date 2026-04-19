# src/extraction/interpretation.py
"""LLM-based structuring of vision transcriptions into biographical data."""

import json
import re
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction.schema import PERSON_SCHEMA
from src.locality import derive_locality

# Place name corrections applied in code — the LLM doesn't reliably apply
# these from the prompt, so we enforce them here.
_PLACE_CORRECTIONS = {
    "haeltert": "Haaltert",
    "haciltert": "Haaltert",
    "kerkxken": "Kerksken",
    "denderhautem": "Denderhoutem",
    "tiedekérke": "Liedekerke",
    "tiedekerk": "Liedekerke",
    "aygem": "Aaigem",
}


def _correct_place(place: str) -> str:
    """Apply mandatory place name corrections."""
    key = place.strip().lower()
    return _PLACE_CORRECTIONS.get(key, place)


def _remove_self_from_spouses(person: dict) -> None:
    """Remove entries from spouses that match the deceased's own name."""
    first = (person.get("first_name") or "").lower().split()
    last = (person.get("last_name") or "").lower().split()
    if not first or not last:
        return

    cleaned = []
    for spouse in person.get("spouses", []):
        spouse_lower = spouse.lower()
        # Check if spouse entry contains both first and last name of deceased
        has_first = any(f in spouse_lower for f in first)
        has_last = all(l in spouse_lower for l in last)
        if not (has_first and has_last):
            cleaned.append(spouse)
    person["spouses"] = cleaned


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

    # Correct OCR-garbled place names
    for field in ("birth_place", "death_place"):
        if isinstance(person.get(field), str):
            person[field] = _correct_place(person[field])

    # Remove the deceased's own name from the spouses list
    _remove_self_from_spouses(person)

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
    existing_source["transcription"] = transcription
    existing["source"] = existing_source

    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
