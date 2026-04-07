# src/extraction/ocr.py
"""Tesseract OCR text extraction from scanned images."""

from pathlib import Path

from PIL import Image
import pytesseract

__all__ = ["extract_text"]


def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Creates the output file even
    if no text is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    raw = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(raw)
