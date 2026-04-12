# Development Guide

## Running the Application

```bash
./run.sh                              # Checks deps, creates venv, starts server
# or directly:
.venv/bin/python -m src.main          # Starts on random available port
```

The browser opens automatically to `http://localhost:<port>`.

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

All tests use `tmp_path` fixtures and mock external dependencies (Tesseract, LLM APIs). No network access or real images needed.

## Project Conventions

- **Always use `.venv/bin/python`**, never global Python.
- **Dates:** ISO 8601 (`YYYY-MM-DD`) internally. Dutch month names (`21 december 1913`) in derived output filenames.
- **Card identity:** UUID4 assigned at match confirmation. Used as JSON filename and API path. Never changes.
- **Filenames:** `Surname Firstname Birthplace bidprentje DD month YYYY` — derived, not user-edited.
- **Public APIs:** Each package exports through `__init__.py` with `__all__`. Import from the package, not submodules.
- **No frameworks:** stdlib HTTP server, vanilla JS. Keep it simple.

## Adding a New LLM Backend

1. Create a class implementing the `LLMBackend` protocol in `src/extraction/llm.py`.
2. The protocol requires a `generate(prompt, system, images)` method returning text.
3. Add a branch in `make_backend()` to instantiate it based on `config.json`.
4. No other changes needed — the pipeline uses `LLMBackend` generically.

## Running the Scraper

```bash
cd scraped && .venv/bin/python scrape.py    # or use VS Code "Scrape Heemkring" config
cd scraped && .venv/bin/python -m pytest test_scrape.py -v  # run scraper tests
```

The scraper has its own venv (`scraped/.venv/`). First run creates `scraped/json/` and `scraped/images/` directories. Re-runs skip already-scraped persons. Check `scraped/scrape.log` for broken links and slug collisions.

## Rebuilding the AI Knowledge Base

```bash
.venv/bin/python docs/ai/rebuild.py          # Regenerate auto-generated docs
.venv/bin/python docs/ai/rebuild.py --quiet  # Silent unless files changed (for hooks)
```

This regenerates `architecture.md`, `api-surface.md`, and `data-model.md` from source.
