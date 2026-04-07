# src/images/__init__.py
"""Image pairing and stitching for memorial card scans.

Public API:
    scan_and_match   — Fuzzy-match front/back image pairs by filename
    stitch_pair      — Stitch two images side-by-side
"""

from src.images.pairing import scan_and_match
from src.images.stitching import stitch_pair

__all__ = ["scan_and_match", "stitch_pair"]
