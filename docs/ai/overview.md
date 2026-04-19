# Memorial Card Digitizer

A web application for digitizing Belgian memorial cards (bidprentjes). Designed for a personal collection of ~50-200 historical cards, each with a front photograph and back biographical text.

## Pipeline

The application runs a 3-phase workflow via a browser-based UI:

1. **Match** — Scans the `input/` directory, fuzzy-matches front/back image pairs by filename similarity, and presents them for manual confirmation. Each confirmed pair gets a UUID.

2. **Extract** — Runs a 2-stage pipeline:
   - **Vision read:** A vision model (Qwen2.5-VL 3B via mlx-vlm) reads both card images directly, producing a raw text transcription of biographical content.
   - **Text structure:** A text model (Gemma 3 4B via mlx-lm) takes the transcription and produces structured JSON via constrained decoding (`json_schema`), extracting names, dates, places, and spouses.

3. **Review** — Shows extracted data in a form for human correction. Handles title-casing, date validation, age-at-death calculation, and spouse management.

4. **Export** — Stitches front+back images side-by-side and writes all cards to a consolidated `memorial_cards.json` with derived Dutch-convention filenames.

## Tech Stack

- **Backend:** Python 3, stdlib HTTP server (`http.server`), no frameworks
- **Frontend:** Vanilla JavaScript, single `index.html`, no build tools
- **Vision model:** Qwen2.5-VL 3B via `mlx-vlm` — reads card images directly
- **Text model:** Gemma 3 4B via `mlx-lm` — structures transcription into JSON with constrained decoding
- **Image processing:** Pillow for stitching and image loading

## Scraper (scraped/)

A separate, disposable tool that scrapes existing memorial card data from the Heemkring Haaltert website (heemkringhaaltert.be) into the same PERSON_SCHEMA JSON format. Self-contained sub-project with its own venv and dependencies (`httpx`, `beautifulsoup4`, `lxml`).

Scrapes all 28 letter pages (A-Z plus D'h and Ve), parses the HTML tables, converts dates to ISO 8601, splits names using tussenvoegsel-aware logic, and downloads memorial card images. Idempotent — safe to re-run.

## Target Usage

Single user, localhost, personal genealogy archive. Not designed for multi-user or deployment.
