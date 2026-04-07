# Browser-based Review UI

## Purpose

After the extraction pipeline runs (OCR + date verification + LLM interpretation), the user needs a way to review and correct the structured data before it's finalized. The review UI shows the original scanned memorial card alongside a pre-filled form with the LLM's best guess, letting the user fix mistakes and approve each card.

## Architecture

### Server (`src/review.py`)

A single-file HTTP server using Python's built-in `http.server` module. No new dependencies.

Launched as a new CLI command: `python -m src.main review`. Opens the browser automatically on startup.

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the static HTML review page |
| `GET` | `/api/cards` | Returns list of all cards (derived from files in `output/json/`) |
| `GET` | `/api/cards/<id>` | Returns JSON data + front/back image paths for one card |
| `PUT` | `/api/cards/<id>` | Saves corrected JSON back to the same file in `output/json/` |
| `GET` | `/images/<path>` | Serves original scan images from `input/` |

The card `<id>` is the JSON filename stem (URL-encoded).

### Frontend (single static HTML file with inline JS/CSS)

Embedded in the Python server as a string or served from a single file. No build step, no framework.

#### Layout

- **Left side:** Card image viewer with a front/back toggle button. Front image is the base filename from `input/`, back image has the ` 1` suffix.
- **Right side:** Form with editable fields pre-filled from the JSON:
  - First name (text)
  - Last name (text)
  - Birth date (text, ISO format)
  - Birth place (text)
  - Death date (text, ISO format)
  - Death place (text)
  - Age at death (number, nullable)
  - Spouse (text, nullable)
  - Father (text, nullable)
  - Mother (text, nullable)
  - Notes (read-only list, displays LLM reasoning)

#### Navigation

- Previous / Next buttons
- Card counter display (e.g., "3 / 47")
- Linear pagination through all cards, no filtering

#### Save

- "Approve" button writes the form data back via `PUT /api/cards/<id>`
- Overwrites the existing JSON file in `output/json/`
- The `source` field in the JSON is preserved as-is

## CLI Integration

New command added to the existing CLI in `src/main.py`:

```
python -m src.main review    # launch review server
python -m src.main merge     # existing
python -m src.main extract   # existing
python -m src.main all       # existing (merge + extract)
```

The `review` command:
1. Checks that `output/json/` exists and has files
2. Starts the HTTP server on a free local port
3. Opens the default browser to the review page
4. Runs until the user stops it (Ctrl+C)

## Scope Boundaries

- Localhost only, no authentication
- No undo — re-run extraction with `--force` to reset
- No filtering, search, or sorting — linear card-by-card review
- No new Python dependencies
