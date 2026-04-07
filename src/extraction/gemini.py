# src/extraction/gemini.py
"""Gemini API client creation and retry wrapper."""

import json
import time
from pathlib import Path

from google import genai
from google.genai.errors import ClientError

__all__ = ["make_gemini_client"]

_MAX_RETRIES = 3


def make_gemini_client(config_path: Path) -> genai.Client:
    """Create a Gemini client from the config file.

    Reads 'gemini_api_key' from the JSON config at config_path.
    """
    config = json.loads(config_path.read_text())
    return genai.Client(api_key=config["gemini_api_key"])


def _call_gemini(client: genai.Client, **kwargs):
    """Call Gemini with automatic retry on rate limit (429) errors.

    Retries up to _MAX_RETRIES times, waiting 60s between attempts
    when a 429 status is received.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(**kwargs)
        except ClientError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                wait = 60
                print(f"        Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
