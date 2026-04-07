# src/images/__init__.py
"""Image pairing and stitching for memorial card scans.

Public API:
    find_pairs   — Detect front/back image pairs by filename convention
    stitch_pair  — Stitch two images side-by-side
    merge_all    — Batch stitch all pairs
"""

from src.images.pairing import find_pairs
from src.images.stitching import stitch_pair, merge_all

__all__ = ["find_pairs", "stitch_pair", "merge_all"]
