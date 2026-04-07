# src/extraction/date_verification.py
"""Verify OCR-read year digits by visual cross-check with Gemini."""

import re
from pathlib import Path

from PIL import Image
from google import genai
from google.genai import types
import pytesseract

from src.extraction.gemini import _call_gemini
from src.extraction.schema import GEMINI_MODEL

_YEAR_RE = re.compile(r"^\d{4}$")


def verify_dates(
    image_path: Path,
    text_path: Path,
    client: genai.Client,
    conflicts_dir: Path | None = None,
) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking Gemini.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to Gemini for visual verification.
    If Gemini reads a different year, the text file is updated in place and
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
        llm_year = _ask_gemini_for_year(client, crop)
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


def _ask_gemini_for_year(client: genai.Client, crop: Image.Image) -> str | None:
    """Send a cropped year image to Gemini and return the read year, or None."""
    resp = _call_gemini(
        client,
        model=GEMINI_MODEL,
        contents=[
            "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
            crop,
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=16,
        ),
    )
    if not resp.text:
        return None
    cleaned = resp.text.strip().rstrip(",.")
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
