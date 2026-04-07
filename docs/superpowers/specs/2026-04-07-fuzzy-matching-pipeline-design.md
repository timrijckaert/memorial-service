# Fuzzy Image Matching & Pipeline Gating

## Problem

The current front/back image pairing relies on a hard filename convention: the back scan has `" 1"` appended before the extension (e.g., `Name.jpeg` / `Name 1.jpeg`). Since filenames are manually assigned, this convention is fragile — typos, different naming styles, and inconsistent suffixes cause missed or wrong pairs. There is no way to verify or correct matches before they enter the pipeline.

## Solution

Replace the hard-coded pairing with fuzzy filename matching, a UI for reviewing/correcting matches, and pipeline gating that requires confirmed pairs before extraction.

## Pipeline Phases

The app changes from **Merge → Extract → Review** to **Match → Extract → Review**.

- **Match**: Scan input directory, run fuzzy matching, present pairs for confirmation. Stitching happens automatically when a pair is confirmed.
- **Extract**: OCR + LLM pipeline. Only operates on confirmed pairs and singles from Match.
- **Review**: Unchanged — edit and approve extracted data.

The current `Merge` tab is removed. Its stitching functionality is folded into the Match confirmation step.

## Fuzzy Matching Algorithm

### Input
All image files (JPEG/JPG/PNG) in the input directory.

### Normalization
- Strip file extension
- Lowercase
- Collapse whitespace
- Remove common suffixes like `" 1"`, `"_back"`, `"_achterkant"` before scoring

### Scoring
Each image is scored against every other image using a combination of:
- **Token overlap**: Shared words (name parts, dates) as a proportion of total unique tokens
- **Sequence similarity**: `difflib.SequenceMatcher` ratio on the normalized filename strings — handles typos, minor reordering

The two scores are combined into a single 0-100% confidence score.

### Pairing
- Build a full similarity matrix
- Greedy pairing: take the highest-scoring pair, remove both from the pool, repeat
- Images with no match above a minimum threshold (e.g., 20%) remain unmatched

### No external dependencies
Python's `difflib` is sufficient for filename-length strings. No need for libraries like `fuzzywuzzy` or `rapidfuzz`.

## Image Metadata

At scan time, read via PIL for each image:
- **Dimensions**: width x height in pixels
- **DPI**: from EXIF/image info (fallback: "unknown")
- **File size**: from filesystem

This metadata is displayed in the Match UI to help distinguish similar images. It is not persisted beyond the matching phase.

## Match UI

### Main View: Sorted Pair List

A single flat list of all proposed pairs, sorted by confidence score (lowest first, so problems surface immediately).

**Top bar** shows summary counts:
- Confirmed pairs count
- Needs-review count
- Unmatched count
- "Confirm All Pairs" button (bulk action)
- "Proceed to Extract" button (disabled until all images are resolved)

**Each pair row** shows:
- Score badge (color-coded: green ≥80%, amber 50-79%, red <50%)
- Thumbnail previews of both images side by side
- Metadata per image: filename, dimensions, DPI, file size
- Actions: "Confirm" and "Unmatch"
- High-confidence pairs (≥80%) are pre-confirmed (shown with a green checkmark) but can still be unmatched if the user spots an error

**Unmatched section** at the bottom shows images with no suggested pair:
- Thumbnail, filename, metadata per image
- "Find match..." button to open manual pairing
- Cards displayed in a compact grid

### Manual Pairing: Find Match

When clicking "Find match..." on an unmatched image:
- Selected image pinned at top with preview and metadata
- All other unmatched images listed below, ranked by fuzzy score against the selected image
- Filter bar to narrow candidates by filename
- "Pair" button on each candidate to create the match
- "Mark as single (no back)" at the bottom for images that genuinely have no partner
- "Back to list" to return without pairing

### Actions

- **Confirm**: Accept the proposed pair. Triggers auto-stitching in the background.
- **Unmatch**: Break a pair. Both images return to the unmatched pool.
- **Pair** (manual): Link two unmatched images. The new pair appears in the list for confirmation.
- **Mark as single**: Flag an image as having no partner. It will appear in Extract as a standalone item (one-sided OCR).
- **Confirm All**: Bulk-confirm all proposed pairs at once.

### Gating

"Proceed to Extract" is enabled only when every image in the input directory is resolved — either part of a confirmed pair or marked as single.

## Extract Tab Changes

- No longer scans the filesystem directly
- Receives the list of confirmed pairs and singles from the Match phase
- Singles are processed with one-sided OCR (front only or back only)
- All other Extract behavior (OCR, date verification, LLM extraction, progress UI) remains unchanged

## Backend API

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/match/scan` | Scan input directory, run fuzzy matching, return pairs with scores and image metadata |
| POST | `/match/confirm` | Confirm a pair (triggers background stitching) |
| POST | `/match/unmatch` | Break a pair, return both images to unmatched pool |
| POST | `/match/pair` | Manually pair two images by filename |
| POST | `/match/single` | Mark an image as single (no partner) |

### Response Format for `/match/scan`

```json
{
  "pairs": [
    {
      "image_a": {
        "filename": "Name.jpeg",
        "width": 2480,
        "height": 3508,
        "dpi": 300,
        "file_size_bytes": 2100000
      },
      "image_b": {
        "filename": "Name 1.jpeg",
        "width": 2480,
        "height": 3508,
        "dpi": 300,
        "file_size_bytes": 1800000
      },
      "score": 94,
      "status": "suggested"
    }
  ],
  "unmatched": [
    {
      "filename": "losse_scan_003.jpeg",
      "width": 1200,
      "height": 1600,
      "dpi": 150,
      "file_size_bytes": 900000
    }
  ]
}
```

## Files Changed

| File | Change |
|------|--------|
| `src/images/pairing.py` | Replace with fuzzy matching module (new algorithm, metadata reading) |
| `src/images/stitching.py` | No changes (called on confirm instead of batch) |
| `src/web/server.py` | Add `/match/*` endpoints, update extract to use match results |
| `src/web/static/app.js` | Replace Merge tab with Match tab UI |
| `src/web/static/style.css` | Styles for match UI (pair rows, score badges, unmatched cards) |
| `src/web/static/index.html` | Update navigation tabs (Merge → Match) |
| `tests/test_pairing.py` | Rewrite for fuzzy matching logic |

## Out of Scope

- Visual/content-based image matching (comparing image pixels)
- Persisting match state across server restarts (re-scan on load)
- Image rotation or orientation detection
- Batch import from multiple directories
