# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one  — Run the full 4-step pipeline for one card pair
    make_backend — Create an LLM backend from config
    LLMBackend   — LLM backend abstraction
    PERSON_SCHEMA — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.llm import make_backend, LLMBackend
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_backend", "LLMBackend", "PERSON_SCHEMA"]
