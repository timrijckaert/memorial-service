# Web Control Panel Design

Replace the CLI-driven workflow with a web UI that serves as the single entry point for merge, extraction, and review.

## Context

Today the pipeline is controlled via CLI subcommands (`merge`, `extract`, `review`). The web UI only handles review. This design promotes the web UI to be the main interface, with the CLI modules (`merge.py`, `extract.py`) serving as libraries that the web server calls into.

## Architecture

### New file: `server.py`

A new HTTP server module that becomes the application entry point. It:

- Serves a single-page application (HTML/JS/CSS, inline as today)
- Exposes REST API routes for merge, extraction, and review
- Imports and delegates to existing modules: `merge.py`, `extract.py`, and the data-access layer extracted from `review.py`

### Refactored: `review.py`

Strip the HTTP server and HTML-serving code out of `review.py`. Keep only the data-access functions:

- `list_cards(json_dir)` — returns sorted list of card IDs
- `load_card(json_dir, input_dir, card_id)` — returns card data + image paths
- `save_card(json_dir, card_id, data)` — saves corrected data, preserves `source` field

These become the shared data layer that `server.py` calls for the Review section.

### Updated: `main.py`

The default command becomes starting the web server. CLI subcommands (`merge`, `extract`) remain available for scripting and automation.

## UI Sections

The app has three sections accessible via top navigation tabs: **Merge**, **Extract**, **Review**.

### Merge Section

1. On load, scan `input/` for front/back pairs using existing `merge.py` pairing logic.
2. Display a grid of detected pairs showing front and back thumbnails side by side, with the card name below each pair.
3. Highlight errors — orphaned files with no matching front or back are shown with a red border and a "missing front/back" label.
4. A "Merge All" button triggers stitching of all valid pairs.
5. After merge completes, the grid updates to show the stitched results with a success/error summary at the top (e.g., "8 merged successfully, 1 skipped").
6. If merged files already exist in `output/`, show them on page load (returning to the page doesn't lose results).
7. A hint tells the user to drop files in `input/` and refresh if no pairs are detected.

### Extract Section

1. On load, show a list of all merged cards in `output/` that are eligible for extraction.
2. An "Extract All" button starts sequential processing on a background thread.
3. During processing, the UI shows:
   - **Current card** highlighted with a step-by-step progress bar: OCR Front → OCR Back → Date Verify → LLM Extract. Completed steps are green, the active step pulses, future steps are dimmed.
   - **OCR text preview** for the current card as it becomes available, alongside a thumbnail of the card image.
   - **Card list** below showing all cards with their status: done (green check), in progress (pulsing dot), queued (dimmed), or error (red).
   - **Summary counters** at the top: done, in progress, queued.
4. Completed cards show a "Review →" deep-link that navigates to the Review section with that card pre-selected.
5. A "Cancel" button stops processing after the current card finishes.
6. Cards that already have a JSON file in `output/json/` are skipped. A "Force re-extract" checkbox overrides this.
7. If Ollama is not available, show a clear error message before allowing extraction to start.
8. If OCR or LLM fails on a card, mark it as "error" in the list with the reason, and continue to the next card.

### Review Section

The existing review UI, integrated into the app:

1. Split layout — image viewer on the left (with Front/Back toggle), editable form on the right.
2. Form fields: first name, last name, birth date, birth place, death date, death place, age at death, spouses (dynamic list), and read-only LLM notes.
3. Prev/Next navigation and card counter for batch review.
4. "Approve" button saves corrections via the API.
5. Deep-link support: navigating to a specific card ID (from the Extract section's "Review →" link) opens the Review section with that card pre-selected. Prev/Next continues through the full batch from there.

## API Routes

### Existing (from review, unchanged behavior)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cards` | Sorted list of card IDs |
| GET | `/api/cards/<id>` | Card data + image references |
| PUT | `/api/cards/<id>` | Save corrected card data |
| GET | `/images/<filename>` | Serve image from `input/` |

### New: Merge

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/merge/pairs` | Detected front/back pairs with thumbnail paths |
| POST | `/api/merge` | Trigger merge of all valid pairs. Returns results synchronously (merge is fast). |

### New: Extract

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/extract/cards` | List of cards eligible for extraction with current status |
| POST | `/api/extract` | Start sequential extraction on background thread |
| GET | `/api/extract/status` | Current processing state: queue, current card, step, done list, errors |
| POST | `/api/extract/cancel` | Stop after current card finishes |

### New: Images

| GET | `/output-images/<filename>` | Serve merged images from `output/` (for merge preview grid and extract thumbnails) |

## Background Worker

A single `threading.Thread` handles extraction:

- Started when the user clicks "Extract All" via `POST /api/extract`.
- Processes cards one by one, sequentially. No `ThreadPoolExecutor` — single-threaded for simplicity and clear UI feedback.
- Updates a shared in-memory state dict as it progresses:

```python
{
    "status": "running",       # running | idle | cancelled
    "current": {
        "card_id": "Pieters Agnes ...",
        "step": "date_verify",  # ocr_front | ocr_back | date_verify | llm_extract
    },
    "done": ["De Smet Maria ...", "Van Damme Jan ..."],
    "errors": [{"card_id": "...", "reason": "..."}],
    "queue": ["Callebaut Rene ...", "De Wolf Hendrik ..."],
}
```

- The state dict is protected by a `threading.Lock`.
- Cancel: `POST /api/extract/cancel` sets a flag. The worker checks it between cards and stops cleanly. Status becomes `"cancelled"`.
- The web server reads this dict to serve `GET /api/extract/status`.
- Navigating away, refreshing, or closing the browser has no effect on the worker thread.

## Frontend Polling

- During active merge or extraction, the frontend polls the corresponding status endpoint every 1–2 seconds via `setInterval`.
- Polling stops when the operation completes (status is `idle` or `cancelled`) or the user navigates to a different section.
- No WebSocket complexity — polling is sufficient for sequential processing with 1–2 second granularity.

## Single Page Application

The app is a single HTML page with three sections toggled via JavaScript (no page reloads). Navigation tabs switch the visible section. The URL hash tracks the active section and card ID for deep-linking:

- `#merge` — Merge section
- `#extract` — Extract section
- `#review` — Review section (card list)
- `#review/<card_id>` — Review section with specific card selected

## Error Handling

- **Orphaned files (merge):** Shown in the pair preview grid with a red "missing front/back" indicator. These are excluded from the merge operation.
- **OCR failure (extract):** Card marked as "error" in the queue list with the reason. Worker continues to the next card.
- **Ollama unavailable (extract):** Check before starting. Show a clear error: "Ollama is not running. Start it with `ollama serve`."
- **LLM parse failure (extract):** Card marked as "error" with reason. Worker continues.
- **Already processed (extract):** Cards with existing JSON in `output/json/` are skipped unless the "Force re-extract" checkbox is enabled.

## Testing

- **Existing tests stay:** `test_pairing.py`, `test_stitching.py`, `test_ocr.py`, `test_verify_dates.py`, `test_interpret.py` are unaffected since the underlying modules don't change.
- **`test_review.py` adapts:** Tests for data-access functions (`list_cards`, `load_card`, `save_card`) stay. HTTP-specific tests move to test the new `server.py` routes.
- **New `test_server.py`:** Tests for all new API routes — merge trigger, merge status, extract start, extract status polling, extract cancel, image serving, deep-link navigation.
- **Worker tests:** Sequential processing order, error handling (skip and continue), cancel flag behavior.

## Out of Scope

- File upload via browser (files are dropped in `input/` manually)
- Authentication (localhost only)
- Database (JSON files remain the storage layer)
- Real-time updates via WebSocket (polling is sufficient)
