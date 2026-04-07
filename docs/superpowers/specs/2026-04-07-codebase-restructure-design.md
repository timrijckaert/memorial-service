# Codebase Restructure Design

## Goal

Restructure the memorial-service codebase from a flat module layout into a clean package architecture. Separate business logic from HTTP/UI concerns, make public APIs explicit, and improve navigability without changing any functionality.

## Context

The codebase was built incrementally with AI assistance and has grown to ~1,450 lines of Python across 5 modules. The main pain points:

- `server.py` (982 lines) mixes HTTP routing, background threading, business orchestration, and ~670 lines of inlined HTML/CSS/JS
- `extract.py` has long functions (up to 74 lines) doing multiple things
- No clear distinction between public API and internal helpers
- Hard to navigate — opening a file doesn't quickly tell you what it does or what you should use

The app is local-only (localhost, opened in browser on same machine). Philosophy: keep it simple, functionality above form.

## New Project Structure

```
src/
├── __init__.py
├── main.py                        # Entry point (slim, just wires things together)
│
├── extraction/                    # OCR + LLM interpretation pipeline
│   ├── __init__.py                # Public API: extract_one, make_gemini_client, PERSON_SCHEMA
│   ├── ocr.py                     # extract_text() — Tesseract OCR
│   ├── date_verification.py       # verify_dates() — Gemini visual cross-check
│   ├── interpretation.py          # interpret_text() — Gemini structured extraction
│   ├── pipeline.py                # extract_one() — orchestrates the 4-step pipeline
│   ├── schema.py                  # PERSON_SCHEMA, shared constants
│   └── gemini.py                  # Gemini client creation + retry wrapper
│
├── images/                        # Image pairing and stitching
│   ├── __init__.py                # Public API: find_pairs, stitch_pair, merge_all
│   ├── pairing.py                 # find_pairs()
│   └── stitching.py               # stitch_pair(), merge_all()
│
├── review/                        # Card data CRUD
│   ├── __init__.py                # Public API: list_cards, load_card, save_card
│   └── cards.py                   # All review functions
│
└── web/                           # HTTP server + UI
    ├── __init__.py                # Public API: make_server
    ├── server.py                  # AppHandler, make_server (HTTP routing only)
    ├── worker.py                  # ExtractionWorker (background thread)
    └── static/                    # Served as static files
        ├── index.html
        ├── style.css
        └── app.js
```

## Package Public APIs

Each package's `__init__.py` re-exports only what outside code should use. Everything else is internal.

### `extraction/`

```python
__all__ = ["extract_one", "make_gemini_client", "PERSON_SCHEMA"]
```

- `extract_one(...)` — runs the full 4-step pipeline for one card pair
- `make_gemini_client(config_path)` — creates the Gemini client from config
- `PERSON_SCHEMA` — the JSON schema (needed by tests)

Internal (not exported): `_call_gemini()`, `extract_text()`, `verify_dates()`, `interpret_text()`. These are used within the package but not by the server or main. Still individually testable via direct imports (e.g. `from src.extraction.ocr import extract_text`).

### `images/`

```python
__all__ = ["find_pairs", "stitch_pair", "merge_all"]
```

All three are needed by the server. Small package, nothing hidden.

### `review/`

```python
__all__ = ["list_cards", "load_card", "save_card"]
```

`_find_image()` stays private — implementation detail of `load_card`.

### `web/`

```python
__all__ = ["make_server"]
```

`ExtractionWorker` and `AppHandler` are internal. Only `make_server` is needed by `main.py`.

## Dataclasses

Replace raw dicts with typed dataclasses in two places:

### `extraction/pipeline.py`

```python
@dataclass
class ExtractionResult:
    front_name: str
    ocr_done: bool = False
    verify_corrections: int = 0
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)
    date_fixes: list[str] = field(default_factory=list)
```

### `web/worker.py`

```python
@dataclass
class CardError:
    card_id: str
    reason: str

@dataclass
class ExtractionStatus:
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    current: dict | None = None
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)
```

Limited to these two spots. Review/cards module stays with plain dicts since it's just loading/saving JSON.

## Static File Serving

The inlined HTML/CSS/JS (670 lines) moves out of Python into separate files:

- `web/static/index.html` — HTML structure with `<link>` and `<script>` tags
- `web/static/style.css` — all CSS (~130 lines)
- `web/static/app.js` — all JS (~465 lines), vanilla, no frameworks

Serving approach:
- `server.py` resolves `static/` directory path once at startup
- `GET /` serves `index.html`
- `GET /static/<filename>` served by a generic `_serve_static()` method
- Same path traversal protection already used for `_serve_image()`

No bundlers, no JS modules. Just one file per language.

## Test Strategy

Existing tests (7 modules, ~450 lines) stay as the safety net.

### Import updates

All existing tests get import path updates:
- `from src.extract import ...` becomes `from src.extraction.ocr import ...` (etc.)
- Test logic stays the same

### New test coverage

| File | What it tests |
|------|--------------|
| `test_gemini.py` | Retry logic in isolation (currently tested indirectly) |
| `test_pipeline.py` | `extract_one` orchestration: step order, error handling at each stage, callback reporting |
| `test_worker.py` | `ExtractionWorker` threading: start, cancel, status transitions |
| `test_static.py` | Static file serving: correct content types, path traversal protection |

### Approach

1. Update all existing test imports first
2. Run full suite to confirm nothing broke
3. Add new tests for the gaps listed above

No rewriting existing tests. No changing test patterns.

## What Does NOT Change

- All existing functionality stays identical
- The web UI looks and behaves exactly the same
- The extraction pipeline processes cards the same way
- Prompt files stay in `prompts/`
- Config file stays at `config.json`
- Input/output directory structure unchanged
- `main.py` remains the sole entry point
