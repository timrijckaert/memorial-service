# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one         — Run the full 4-step pipeline for one card pair
    make_gemini_client  — Create a Gemini API client from config
    PERSON_SCHEMA       — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.gemini import make_gemini_client
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_gemini_client", "PERSON_SCHEMA"]
