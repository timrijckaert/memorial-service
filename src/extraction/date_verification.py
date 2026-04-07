# src/extraction/date_verification.py
"""Verify OCR-read year digits by visual cross-check with an LLM backend."""

import re
from pathlib import Path

from PIL import Image
import pytesseract

from src.extraction.llm import LLMBackend

_YEAR_RE = re.compile(r"^\d{4}$")


def verify_dates(
    image_path: Path,
    text_path: Path,
    backend: LLMBackend,
    conflicts_dir: Path | None = None,
) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking an LLM.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to the LLM backend for visual verification.
    If the LLM reads a different year, the text file is updated in place and
    the crop image is saved to conflicts_dir for manual review.

    Returns a list of corrections made (empty if all years match).
    """
    image = Image.open(image_path)
    data = pytesseract.image_to_data(
        image, lang="nld", output_type=pytesseract.Output.DICT
    )

    years = _find_year_regions(data)
    if not years:
        return []

    corrections = []
    text = text_path.read_text()

    for entry in years:
        crop = _crop_year_region(image, entry)
        llm_year = _ask_llm_for_year(backend, crop)
        if llm_year is None:
            continue

        if _should_correct(entry["ocr_year"], llm_year):
            text = text.replace(entry["ocr_year"], llm_year, 1)
            corrections.append(f"{entry['ocr_year']} -> {llm_year}")

            if conflicts_dir:
                _save_conflict_crop(conflicts_dir, image_path.stem, entry["ocr_year"], llm_year, crop)

    if corrections:
        text_path.write_text(text)

    return corrections


def _find_year_regions(data: dict) -> list[dict]:
    """Find 4-digit year-like words in Tesseract bounding-box data."""
    years = []
    for i, word in enumerate(data["text"]):
        clean_word = word.strip().rstrip(",.")
        if _YEAR_RE.match(clean_word):
            years.append({
                "ocr_year": clean_word,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            })
    return years


def _crop_year_region(image: Image.Image, entry: dict, pad: int = 10) -> Image.Image:
    """Crop an image region around a detected year word."""
    return image.crop((
        max(0, entry["left"] - pad),
        max(0, entry["top"] - pad),
        entry["left"] + entry["width"] + pad,
        entry["top"] + entry["height"] + pad,
    ))


def _ask_llm_for_year(backend: LLMBackend, crop: Image.Image) -> str | None:
    """Send a cropped year image to the LLM backend and return the read year, or None."""
    text = backend.generate_vision(
        "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
        crop,
        temperature=0,
        max_tokens=16,
    )
    if not text:
        return None
    cleaned = text.strip().rstrip(",.")
    return cleaned if _YEAR_RE.match(cleaned) else None


def _should_correct(ocr_year: str, llm_year: str) -> bool:
    """Check if the LLM year is different from OCR and within valid range (1800-1950)."""
    return llm_year != ocr_year and 1800 <= int(llm_year) <= 1950


def _save_conflict_crop(
    conflicts_dir: Path, stem: str, ocr_year: str, llm_year: str, crop: Image.Image
) -> None:
    """Save a conflict crop image for manual review."""
    conflicts_dir.mkdir(exist_ok=True)
    conflict_path = conflicts_dir / f"{stem}_ocr{ocr_year}_llm{llm_year}.png"
    crop.save(conflict_path)
