# src/images/__init__.py
"""Image pairing and stitching for memorial card scans.

Public API:
    scan_and_match   — Fuzzy-match front/back image pairs by filename
    find_pairs       — Legacy: detect front/back pairs by filename convention
    stitch_pair      — Stitch two images side-by-side
    merge_all        — Batch stitch all pairs
"""

from src.images.pairing import scan_and_match, find_pairs
from src.images.stitching import stitch_pair, merge_all

__all__ = ["scan_and_match", "find_pairs", "stitch_pair", "merge_all"]
