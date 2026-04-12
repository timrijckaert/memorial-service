# Memorial Card Digitizer

A web application for digitizing Belgian memorial cards (bidprentjes). Designed for a personal collection of ~50-200 historical cards, each with a front photograph and back biographical text.

## Pipeline

The application runs a 4-stage pipeline via a browser-based UI:

1. **Match** — Scans the `input/` directory, fuzzy-matches front/back image pairs by filename similarity, and presents them for manual confirmation. Each confirmed pair gets a UUID.

2. **Extract** — Runs OCR (Tesseract, Dutch language) on both sides, then sends the text through an LLM (Gemini or Ollama) to extract structured biographical data: names, dates, places, spouses.

3. **Review** — Shows extracted data in a form for human correction. Handles title-casing, date validation, age-at-death calculation, and spouse management.

4. **Export** — Stitches front+back images side-by-side and writes all cards to a consolidated `memorial_cards.json` with derived Dutch-convention filenames.

## Tech Stack

- **Backend:** Python 3, stdlib HTTP server (`http.server`), no frameworks
- **Frontend:** Vanilla JavaScript, single `index.html`, no build tools
- **OCR:** Tesseract via `pytesseract` (Dutch language pack)
- **LLM:** Pluggable backend — Gemini API (cloud) or Ollama (local)
- **Image processing:** Pillow for stitching
- **Async:** `asyncio` for parallel OCR, sequential LLM processing

## Scraper (scraped/)

A separate, disposable tool that scrapes existing memorial card data from the Heemkring Haaltert website (heemkringhaaltert.be) into the same PERSON_SCHEMA JSON format. Self-contained sub-project with its own venv and dependencies (`httpx`, `beautifulsoup4`, `lxml`).

Scrapes all 28 letter pages (A-Z plus D'h and Ve), parses the HTML tables, converts dates to ISO 8601, splits names using tussenvoegsel-aware logic, and downloads memorial card images. Idempotent — safe to re-run.

## Target Usage

Single user, localhost, personal genealogy archive. Not designed for multi-user or deployment.
