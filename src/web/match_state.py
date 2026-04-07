# src/web/match_state.py
"""In-memory state management for the match phase."""

import threading
from pathlib import Path

from src.images.pairing import scan_and_match, read_image_metadata, similarity_score, normalize_filename
from src.images.stitching import stitch_pair


class MatchState:
    """Manages match phase state: pairs, unmatched images, singles, confirmations."""

    def __init__(self, input_dir: Path, output_dir: Path):
        self._input_dir = input_dir
        self._output_dir = output_dir
        self._lock = threading.Lock()
        self._pairs: list[dict] = []
        self._unmatched: list[dict] = []
        self._singles: list[str] = []
        self._metadata: dict[str, dict] = {}

    def scan(self) -> dict:
        """Scan input directory and run fuzzy matching. Returns snapshot."""
        result = scan_and_match(self._input_dir)

        with self._lock:
            self._pairs = result["pairs"]
            self._unmatched = result["unmatched"]
            self._singles = []
            self._metadata = {}
            for pair in self._pairs:
                self._metadata[pair["image_a"]["filename"]] = pair["image_a"]
                self._metadata[pair["image_b"]["filename"]] = pair["image_b"]
            for item in self._unmatched:
                self._metadata[item["filename"]] = item

        return self.get_snapshot()

    def get_snapshot(self) -> dict:
        """Return current state as a serializable dict."""
        with self._lock:
            confirmed_count = sum(
                1 for p in self._pairs if p["status"] in ("confirmed", "auto_confirmed")
            )
            needs_review = sum(
                1 for p in self._pairs if p["status"] == "suggested"
            )
            all_resolved = len(self._unmatched) == 0 and needs_review == 0

            return {
                "pairs": [dict(p) for p in self._pairs],
                "unmatched": [dict(u) for u in self._unmatched],
                "singles": list(self._singles),
                "confirmed_count": confirmed_count,
                "needs_review": needs_review,
                "unmatched_count": len(self._unmatched),
                "all_resolved": all_resolved,
            }

    def confirm(self, filename_a: str, filename_b: str) -> dict:
        """Confirm a pair and trigger stitching."""
        with self._lock:
            for pair in self._pairs:
                a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
                if {a, b} == {filename_a, filename_b}:
                    pair["status"] = "confirmed"
                    break
            else:
                return {"status": "not_found"}

        # Stitch in background-safe way (outside lock)
        path_a = self._input_dir / filename_a
        path_b = self._input_dir / filename_b
        output_name = Path(filename_a).stem + ".jpeg"
        output_path = self._output_dir / output_name
        try:
            stitch_pair(path_a, path_b, output_path)
        except Exception:
            pass  # Stitching failure doesn't block confirmation

        return {"status": "confirmed"}

    def unmatch(self, filename_a: str, filename_b: str) -> dict:
        """Break a pair, returning both images to unmatched."""
        with self._lock:
            to_remove = None
            for i, pair in enumerate(self._pairs):
                a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
                if {a, b} == {filename_a, filename_b}:
                    to_remove = i
                    break

            if to_remove is None:
                return {"status": "not_found"}

            pair = self._pairs.pop(to_remove)
            self._unmatched.append(pair["image_a"])
            self._unmatched.append(pair["image_b"])

        return {"status": "unmatched"}

    def manual_pair(self, filename_a: str, filename_b: str) -> dict:
        """Manually pair two unmatched images."""
        with self._lock:
            meta_a = None
            meta_b = None
            new_unmatched = []

            for item in self._unmatched:
                if item["filename"] == filename_a:
                    meta_a = item
                elif item["filename"] == filename_b:
                    meta_b = item
                else:
                    new_unmatched.append(item)

            if meta_a is None or meta_b is None:
                return {"status": "not_found"}

            self._unmatched = new_unmatched

            norm_a = normalize_filename(filename_a)
            norm_b = normalize_filename(filename_b)
            score = similarity_score(norm_a, norm_b)

            self._pairs.append({
                "image_a": meta_a,
                "image_b": meta_b,
                "score": score,
                "status": "suggested",
            })
            self._pairs.sort(key=lambda p: p["score"])

        return {"status": "paired"}

    def mark_single(self, filename: str) -> dict:
        """Mark an unmatched image as single (no partner)."""
        with self._lock:
            found = False
            new_unmatched = []
            for item in self._unmatched:
                if item["filename"] == filename:
                    found = True
                else:
                    new_unmatched.append(item)

            if not found:
                return {"status": "not_found"}

            self._unmatched = new_unmatched
            self._singles.append(filename)

        return {"status": "single"}

    def confirm_all(self) -> dict:
        """Confirm all suggested pairs."""
        to_stitch = []
        with self._lock:
            for pair in self._pairs:
                if pair["status"] == "suggested":
                    pair["status"] = "confirmed"
                    to_stitch.append((
                        pair["image_a"]["filename"],
                        pair["image_b"]["filename"],
                    ))

        for filename_a, filename_b in to_stitch:
            path_a = self._input_dir / filename_a
            path_b = self._input_dir / filename_b
            output_name = Path(filename_a).stem + ".jpeg"
            output_path = self._output_dir / output_name
            try:
                stitch_pair(path_a, path_b, output_path)
            except Exception:
                pass

        return {"status": "confirmed", "count": len(to_stitch)}

    def get_confirmed_items(self) -> tuple[list[tuple[Path, Path]], list[Path]]:
        """Return confirmed pairs and singles as paths for the extract pipeline."""
        with self._lock:
            pairs = []
            for p in self._pairs:
                if p["status"] in ("confirmed", "auto_confirmed"):
                    pairs.append((
                        self._input_dir / p["image_a"]["filename"],
                        self._input_dir / p["image_b"]["filename"],
                    ))
            singles = [self._input_dir / name for name in self._singles]

        return pairs, singles

    def get_scores_for(self, filename: str) -> list[dict]:
        """Get similarity scores between a given file and all other unmatched files."""
        with self._lock:
            others = [u for u in self._unmatched if u["filename"] != filename]

        target_norm = normalize_filename(filename)
        scored = []
        for other in others:
            other_norm = normalize_filename(other["filename"])
            score = similarity_score(target_norm, other_norm)
            scored.append({**other, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored
