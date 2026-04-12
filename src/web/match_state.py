# src/web/match_state.py
"""In-memory state management for the match phase."""

import json
import threading
import uuid
from pathlib import Path

from src.images.pairing import scan_and_match, read_image_metadata, similarity_score, normalize_filename


class MatchState:
    """Manages match phase state: pairs, unmatched images, singles, confirmations."""

    def __init__(self, input_dir: Path, output_dir: Path, json_dir: Path | None = None):
        self._input_dir = input_dir
        self._output_dir = output_dir
        self._json_dir = json_dir or (output_dir / "json")
        self._lock = threading.Lock()
        self._pairs: list[dict] = []
        self._unmatched: list[dict] = []
        self._singles: list[dict] = []
        self._metadata: dict[str, dict] = {}
        self._restored_files: set[str] = set()

    def _assign_card_id(self, front_file: str, back_file: str | None) -> str:
        """Generate a UUID4, write skeleton JSON to json_dir, return UUID string."""
        card_id = str(uuid.uuid4())
        self._json_dir.mkdir(parents=True, exist_ok=True)
        skeleton = {
            "source": {
                "front_image_file": front_file,
                "back_image_file": back_file,
            }
        }
        skeleton_path = self._json_dir / f"{card_id}.json"
        skeleton_path.write_text(json.dumps(skeleton, indent=2))
        return card_id

    def restore(self) -> None:
        """Reconstruct match state from existing JSON files on disk."""
        if not self._json_dir.exists():
            return

        # Read all JSONs, preferring those with person data over skeletons
        candidates = []
        for json_path in self._json_dir.glob("*.json"):
            try:
                data = json.loads(json_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            has_person = "person" in data
            candidates.append((json_path, data, has_person))
        # Sort: extracted cards first, then by path for determinism
        candidates.sort(key=lambda c: (not c[2], c[0]))

        with self._lock:
            restored_files = set()
            orphans = []

            for json_path, data, _has_person in candidates:
                source = data.get("source", {})
                front_file = source.get("front_image_file")
                back_file = source.get("back_image_file")
                card_id = json_path.stem

                if not front_file:
                    continue

                # Skip if this image is already claimed by a previous JSON
                if front_file in restored_files:
                    orphans.append(json_path)
                    continue
                if back_file and back_file in restored_files:
                    orphans.append(json_path)
                    continue

                if not (self._input_dir / front_file).exists():
                    continue
                if back_file and not (self._input_dir / back_file).exists():
                    continue

                if back_file:
                    self._pairs.append({
                        "image_a": {"filename": front_file},
                        "image_b": {"filename": back_file},
                        "score": 100,
                        "status": "auto_confirmed",
                        "card_id": card_id,
                    })
                    restored_files.add(front_file)
                    restored_files.add(back_file)
                else:
                    self._singles.append({
                        "filename": front_file,
                        "card_id": card_id,
                    })
                    restored_files.add(front_file)

            self._restored_files = restored_files

        # Delete orphaned duplicate JSONs outside the lock
        for orphan in orphans:
            orphan.unlink(missing_ok=True)

    def scan(self) -> dict:
        """Scan input directory and run fuzzy matching. Returns snapshot."""
        result = scan_and_match(self._input_dir)

        if self._restored_files:
            result["pairs"] = [
                p for p in result["pairs"]
                if p["image_a"]["filename"] not in self._restored_files
                and p["image_b"]["filename"] not in self._restored_files
            ]
            result["unmatched"] = [
                u for u in result["unmatched"]
                if u["filename"] not in self._restored_files
            ]

        with self._lock:
            new_pairs = result["pairs"]
            new_unmatched = result["unmatched"]
            # Keep restored pairs/singles, add newly scanned ones
            self._pairs = [p for p in self._pairs if p.get("card_id")] + new_pairs
            self._unmatched = new_unmatched
            # Don't clear singles — restored singles should persist
            self._metadata = {}
            for pair in self._pairs:
                self._metadata[pair["image_a"]["filename"]] = pair["image_a"]
                self._metadata[pair["image_b"]["filename"]] = pair["image_b"]
            for item in self._unmatched:
                self._metadata[item["filename"]] = item

            # Assign UUIDs to auto-confirmed pairs
            pairs_needing_ids = [
                p for p in self._pairs
                if p["status"] == "auto_confirmed" and "card_id" not in p
            ]

        # Write skeleton JSONs outside the lock
        for pair in pairs_needing_ids:
            card_id = self._assign_card_id(
                pair["image_a"]["filename"],
                pair["image_b"]["filename"],
            )
            pair["card_id"] = card_id

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
                "singles": [dict(s) for s in self._singles],
                "confirmed_count": confirmed_count,
                "needs_review": needs_review,
                "unmatched_count": len(self._unmatched),
                "all_resolved": all_resolved,
            }

    def confirm(self, filename_a: str, filename_b: str) -> dict:
        """Confirm a pair."""
        with self._lock:
            matched_pair = None
            for pair in self._pairs:
                a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
                if {a, b} == {filename_a, filename_b}:
                    pair["status"] = "confirmed"
                    matched_pair = pair
                    break
            else:
                return {"status": "not_found"}

        # Assign UUID if not already present (e.g. from auto-confirm)
        if "card_id" not in matched_pair:
            card_id = self._assign_card_id(
                matched_pair["image_a"]["filename"],
                matched_pair["image_b"]["filename"],
            )
            matched_pair["card_id"] = card_id
        card_id = matched_pair["card_id"]

        return {"status": "confirmed", "card_id": card_id}

    def unmatch(self, filename_a: str, filename_b: str) -> dict:
        """Break a pair, returning both images to unmatched."""
        removed_card_id = None
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
            removed_card_id = pair.get("card_id")
            self._unmatched.append(pair["image_a"])
            self._unmatched.append(pair["image_b"])
            self._restored_files.discard(pair["image_a"]["filename"])
            self._restored_files.discard(pair["image_b"]["filename"])

        # Delete skeleton JSON outside the lock
        if removed_card_id:
            skeleton_path = self._json_dir / f"{removed_card_id}.json"
            if skeleton_path.exists():
                skeleton_path.unlink()

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

        card_id = self._assign_card_id(filename, None)
        with self._lock:
            self._singles.append({"filename": filename, "card_id": card_id})

        return {"status": "single", "card_id": card_id}

    def confirm_all(self) -> dict:
        """Confirm all suggested pairs."""
        confirmed_count = 0
        newly_confirmed = []
        with self._lock:
            for pair in self._pairs:
                if pair["status"] == "suggested":
                    pair["status"] = "confirmed"
                    confirmed_count += 1
                    if "card_id" not in pair:
                        newly_confirmed.append(pair)

        # Assign UUIDs outside the lock
        for pair in newly_confirmed:
            card_id = self._assign_card_id(
                pair["image_a"]["filename"],
                pair["image_b"]["filename"],
            )
            pair["card_id"] = card_id

        return {"status": "confirmed", "count": confirmed_count}

    def get_confirmed_items(self) -> tuple[list[tuple[str, Path, Path]], list[tuple[str, Path]]]:
        """Return confirmed pairs and singles with card_ids for the extract pipeline."""
        with self._lock:
            pairs = []
            for p in self._pairs:
                if p["status"] in ("confirmed", "auto_confirmed"):
                    pairs.append((
                        p["card_id"],
                        self._input_dir / p["image_a"]["filename"],
                        self._input_dir / p["image_b"]["filename"],
                    ))
            singles = [
                (s["card_id"], self._input_dir / s["filename"])
                for s in self._singles
            ]
        return pairs, singles

    def swap(self, filename_a: str, filename_b: str) -> dict:
        """Swap image_a and image_b in a pair."""
        with self._lock:
            for pair in self._pairs:
                a, b = pair["image_a"]["filename"], pair["image_b"]["filename"]
                if {a, b} == {filename_a, filename_b}:
                    pair["image_a"], pair["image_b"] = pair["image_b"], pair["image_a"]
                    return {"status": "swapped"}
            return {"status": "not_found"}

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
