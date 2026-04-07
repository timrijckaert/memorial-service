# src/extraction/pipeline.py
"""Orchestrates the full extraction pipeline for a single card pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.extraction.llm import LLMBackend

from src.extraction.ocr import extract_text
from src.extraction.date_verification import verify_dates
from src.extraction.interpretation import interpret_text


@dataclass
class ExtractionResult:
    """Result of processing a single card pair through the extraction pipeline."""
    front_name: str
    ocr_done: bool = False
    verify_corrections: int = 0
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)
    date_fixes: list[str] = field(default_factory=list)


def extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    backend: LLMBackend | None,
    system_prompt: str | None,
    user_template: str | None,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """Process extraction for a single pair: OCR, date verification, LLM interpretation.

    Pipeline stages (reported via on_step callback):
      1. ocr_front  — Tesseract OCR on front image
      2. ocr_back   — Tesseract OCR on back image
      3. date_verify — Gemini visual cross-check of year digits
      4. llm_extract — Gemini structured data extraction

    Stages 3-4 only run if a backend is provided.
    """
    result = ExtractionResult(front_name=front_path.name)

    front_text_path = text_dir / f"{front_path.stem}_front.txt"
    back_text_path = text_dir / f"{back_path.stem}_back.txt"

    # OCR Front
    if on_step:
        on_step("ocr_front")
    try:
        extract_text(front_path, front_text_path)
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR front: {e}")
        return result

    # OCR Back
    if on_step:
        on_step("ocr_back")
    try:
        extract_text(back_path, back_text_path)
        result.ocr_done = True
    except Exception as e:
        result.errors.append(f"{front_path.name} OCR back: {e}")
        return result

    # Date verification (LLM visual cross-check)
    if backend:
        if on_step:
            on_step("date_verify")
        try:
            for txt_path, img_path in [
                (front_text_path, front_path),
                (back_text_path, back_path),
            ]:
                corrections = verify_dates(img_path, txt_path, backend, conflicts_dir)
                for c in corrections:
                    result.verify_corrections += 1
                    result.date_fixes.append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result.errors.append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if backend:
        if on_step:
            on_step("llm_extract")
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(
                front_text_path, back_text_path, json_output_path,
                system_prompt, user_template, backend,
            )
            result.interpreted = True
        except Exception as e:
            result.errors.append(f"{front_path.name} interpret: {e}")

    return result
