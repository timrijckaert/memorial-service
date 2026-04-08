# Stable Card ID Design

**Date:** 2026-04-08
**Branch:** feat/async-pipeline

## Problem

Cards are identified by their input image filename stem (e.g., `wynant clementina haaltert juli 1917`). This causes:

1. **Broken deeplinks** — stems contain spaces, special characters, and non-ASCII that require URL encoding. Hash-based navigation (`#review/wynant%20clementina%20...`) is fragile.
2. **No persistence across restarts** — match state is in-memory only. If the server restarts after matching, confirmed pairs are lost.
3. **Identity confusion** — the stem (messy input filename), derived name (clean display name), and export key are three different strings for the same card, with no stable anchor tying them together.

## Solution

Assign a UUID4 to each card at match-confirm time. The UUID becomes the card's identity throughout the pipeline. It is used as the JSON filename, API path parameter, and frontend deeplink target. The messy input filename lives inside the JSON's `source` field for traceability; the derived name is computed for display only.

## Pipeline Flow

```
Match: user confirms pair → UUID assigned, skeleton JSON written
Extract: worker enriches existing JSON with person/notes
Review: user edits card by UUID
Export: reads all JSONs, computes derived names for output files
```

---

## 1. Match Phase — UUID Assignment

### When UUIDs Are Assigned

A UUID is assigned whenever a card is confirmed — whether by user action or auto-confirm:

- `confirm(filename_a, filename_b)` — user clicks confirm on a suggested pair
- `confirm_all()` — user confirms all remaining suggested pairs
- `mark_single(filename)` — user marks an unmatched image as single
- Auto-confirmed pairs (status `auto_confirmed` set during scan)

All four paths call the same internal method to mint the UUID and write the skeleton. `confirm_all()` iterates all suggested pairs and calls this method for each one.

### Skeleton JSON

Written to `output/json/<uuid>.json` at confirm time:

```json
{
  "source": {
    "front_image_file": "scan_047.jpeg",
    "back_image_file": "scan_047_verso.jpeg"
  }
}
```

For singles, `back_image_file` is `null`.

### Pair Data Structure

The pair dict gains a `card_id` field:

```python
{
    "image_a": {"filename": "scan_047.jpeg", ...},
    "image_b": {"filename": "scan_047_verso.jpeg", ...},
    "score": 92,
    "status": "confirmed",
    "card_id": "a1b2c3d4-e5f6-7890-abcd-1234567890ab"
}
```

Singles: `_singles` changes from `list[str]` to `list[dict]` with `{"filename": "...", "card_id": "..."}`.

### Unmatch — Cleanup

**Pairs:** When a confirmed pair is unmatched:

1. Delete `output/json/<uuid>.json` from disk (if it exists — may have been enriched by extraction)
2. Remove `card_id` from the pair
3. Return both images to `_unmatched`

**Singles:** When a single is returned to unmatched (not currently supported, but if added):

1. Delete `output/json/<uuid>.json` from disk
2. Remove the single from `_singles`
3. Return the image to `_unmatched`

If a card is later re-confirmed, it gets a fresh UUID and starts from scratch.

### `get_confirmed_items()` Return Type

Changes from:
```python
tuple[list[tuple[Path, Path]], list[Path]]
```

To:
```python
tuple[list[tuple[str, Path, Path]], list[tuple[str, Path]]]
#     pairs: (card_id, front, back)    singles: (card_id, front)
```

### Auto-Confirmed Pairs

During `scan()`, any pairs that arrive with status `auto_confirmed` from `scan_and_match()` also get UUIDs and skeleton JSONs. This happens in the same `scan()` method, after pairs are stored.

---

## 2. Worker Phase — UUID as Card Identity

### Changes

- Worker receives `(card_id, front_path, back_path)` tuples instead of `(front_path, back_path)`
- `card_name = front_path.stem` becomes `card_id` (the UUID)
- All status tracking uses UUID: `_status.queue`, `_status.in_flight`, `_status.done`
- OCR text files use UUID: `{card_id}_front.txt`, `{card_id}_back.txt`

### JSON Enrichment

The worker no longer creates the JSON file. It reads the existing skeleton and updates it:

```python
json_path = json_dir / f"{card_id}.json"
existing = json.loads(json_path.read_text())
existing["person"] = person_data
existing["notes"] = notes
existing["source"]["front_text_file"] = f"{card_id}_front.txt"
existing["source"]["back_text_file"] = f"{card_id}_back.txt"
json_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
```

This means `interpret_text()` needs to accept the existing skeleton data and merge into it, rather than writing a fresh file.

---

## 3. Review Phase

No structural change. `list_cards()` returns JSON file stems — which are now UUIDs. `load_card()` and `save_card()` work the same way, just with UUID-based filenames.

---

## 4. Server API

All endpoints use UUID as the card identifier. No URL encoding needed (UUIDs contain only `[0-9a-f-]`).

- `GET /api/cards` → `["a1b2c3d4-...", ...]`
- `GET /api/cards/{uuid}` → card data + `derived_name`
- `PUT /api/cards/{uuid}` → update card
- `GET /api/extract/cards` → cards with `card_id` (UUID), `status`, `derived_name`
- `GET /api/match/snapshot` → pairs now include `card_id` field when confirmed

---

## 5. Frontend

- Deeplinks: `#review/a1b2c3d4-e5f6-7890-abcd-1234567890ab` — clean, no encoding
- Extract list: display `derived_name`, navigate by UUID
- Review: `reviewCards` array holds UUIDs
- `encodeURIComponent`/`decodeURIComponent` no longer needed for card IDs (keep for safety, but UUIDs never need it)

---

## 6. Export Phase

No change in logic. Export reads `output/json/*.json`, computes derived filenames for output images and consolidated JSON. The fact that JSON filenames are UUIDs instead of stems is transparent to it.

---

## Files Changed

| File | Change |
|---|---|
| `src/web/match_state.py` | Assign UUID on confirm/mark_single, write skeleton JSON, delete on unmatch, update `_singles` to `list[dict]`, update `get_confirmed_items()` return type |
| `src/web/worker.py` | Accept `(card_id, front, back)` tuples, use UUID for all tracking, update (not create) JSON |
| `src/extraction/interpretation.py` | Accept existing skeleton data, merge extracted person/notes into it |
| `src/web/server.py` | Pass `card_id` through API responses, update extract cards endpoint |
| `src/web/static/app.js` | Use UUID for deeplinks and API calls, display derived_name |
| `src/review/cards.py` | No structural change (already uses JSON file stems) |
| `src/export.py` | No change |
| `tests/test_match_state.py` | Test UUID assignment, skeleton creation, unmatch cleanup |
| `tests/test_worker.py` | Update to use UUID-based card identity |

---

## Out of Scope

- UUID in the match phase URL/deeplinks (match operates on filenames, not card IDs)
- Migrating existing `output/json/` files from stem-based to UUID-based names
- Changing the export consolidated JSON key format (still uses derived name)
