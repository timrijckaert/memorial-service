# AI Knowledge Base Design

**Date:** 2026-04-12
**Status:** Approved

## Problem

Every new AI session starts cold. The agent re-discovers the project structure, pipeline stages, module responsibilities, and conventions by reading source files. This wastes tokens, time, and leads to inconsistent understanding. There is no CLAUDE.md or any AI-facing project harness.

## Goal

Create a self-maintaining markdown knowledge base in `docs/ai/` that gives any AI coding assistant a complete picture of the project in minimal tokens. Auto-generated files stay current via a rebuild script triggered by Claude Code hooks. Hand-written files are maintained by convention.

## Design

### File Structure

```
docs/ai/
├── overview.md          # HAND-WRITTEN — what the project does, who it's for, pipeline stages
├── architecture.md      # AUTO-GENERATED — module map, package responsibilities, dependencies
├── api-surface.md       # AUTO-GENERATED — public functions per package (__init__.py exports)
├── data-model.md        # AUTO-GENERATED — PERSON_SCHEMA, directory layout, file conventions
├── development.md       # HAND-WRITTEN — how to run, test, add backends, project conventions
├── decisions.md         # HAND-WRITTEN — key architectural "why"s distilled from specs
└── rebuild.py           # The generator script for auto-generated files

CLAUDE.md                # Root adapter — points Claude Code into docs/ai/
AGENTS.md                # Root adapter — generic agent instructions
```

### File Contents

#### `overview.md` (hand-written)

- One-paragraph project description: Belgian memorial card digitizer for a personal collection of ~50-200 historical cards with photographs and biographical text.
- The 4-stage pipeline: Match (fuzzy-pair front/back scans) -> Extract (OCR + LLM structured extraction) -> Review (browser UI for human correction) -> Export (stitched images + consolidated JSON).
- Tech stack: Python 3, vanilla JavaScript, Tesseract OCR, Gemini/Ollama LLM backends, stdlib HTTP server. No frameworks.
- Target usage: single user, localhost, personal archive project.

#### `architecture.md` (auto-generated)

- File tree of `src/` with one-line description per file.
- Package dependency graph: which packages import which.
- For each package: its `__init__.py` exports and what they represent.
- HTTP API endpoints extracted from `server.py` route handler patterns (URL -> method mapping).

#### `api-surface.md` (auto-generated)

- For each package's `__init__.py`: every exported name, its function signature, and its docstring (if present).
- Grouped by package: `extraction`, `images`, `review`, `web`.
- Includes key standalone modules: `export.py`, `naming.py`.

#### `data-model.md` (auto-generated)

- `PERSON_SCHEMA` dict extracted from `schema.py`.
- Directory conventions: `input/` (scanned images), `output/json/` (per-card JSON), `output/text/` (OCR text), `output/export/` (final stitched images + consolidated JSON).
- JSON file lifecycle: skeleton (created at match confirm) -> enriched (after LLM extraction) -> reviewed (after human correction) -> exported (consolidated output).

#### `development.md` (hand-written)

- How to run: `./run.sh` or `.venv/bin/python src/main.py`.
- How to test: `.venv/bin/python -m pytest tests/`.
- How to add a new LLM backend: implement the `LLMBackend` protocol in `src/extraction/llm.py`.
- Conventions: always use `.venv/bin/python` (never global), ISO 8601 dates internally, Dutch month names in derived output filenames.

#### `decisions.md` (hand-written)

Key architectural decisions distilled from the 16 existing design specs:

- UUID-based card identity instead of filename-based: filenames change when data is corrected; UUIDs are stable.
- Fuzzy filename matching over visual/content-based matching: simpler, good enough for the naming conventions used in scanning.
- No frameworks (vanilla JS, stdlib HTTP server): project is small, personal, no need for build tools or dependencies.
- Parallel OCR but sequential LLM: OCR is CPU-bound and independent per image; LLM calls share context and benefit from sequential processing.
- Match-phase stitching removed, export-only: stitching during matching was redundant since export handles it; removing it simplified the confirm flow.

### The Rebuild Script (`rebuild.py`)

**Location:** `docs/ai/rebuild.py`

**What it does:**

- Uses Python's `ast` module to parse all `.py` files under `src/`.
- Extracts function and class signatures, docstrings, and `__init__.py` exports.
- Reads `PERSON_SCHEMA` from `src/extraction/schema.py`.
- Scans `src/web/server.py` for route handler patterns (regex matching on path dispatch).
- Scans directory structure for `input/` and `output/` subdirectory conventions.
- Writes three files: `architecture.md`, `api-surface.md`, `data-model.md`.

**What it does NOT do:**

- Touch hand-written files (`overview.md`, `development.md`, `decisions.md`).
- Make network calls or run the application.
- Require any dependencies beyond Python stdlib (`ast`, `os`, `pathlib`, `textwrap`, `json`, `re`).

**Flags:**

- `--quiet`: suppress output unless a file actually changed. For use in hooks.

**Output format:**

Each auto-generated file starts with:

```markdown
<!-- AUTO-GENERATED by docs/ai/rebuild.py — do not edit manually -->
<!-- Last rebuilt: 2026-04-12T17:15:00 -->
```

**Idempotency:** running the script twice with no code changes produces identical output.

### Auto-Update: Claude Code Hooks

A `PostToolUse` hook in `.claude/settings.json` triggers the rebuild script after any file-modifying tool call:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "command": ".venv/bin/python docs/ai/rebuild.py --quiet"
      }
    ]
  }
}
```

**Why PostToolUse instead of a git hook:**

- Catches changes before commit: the AI sees updated docs within the same session.
- No git hook maintenance or setup.
- Only fires during AI sessions, not during manual edits (the user can run `rebuild.py` manually if needed).

### Convention Rules for Hand-Written Files

Added to `CLAUDE.md` so the AI maintains narrative docs:

> When you modify the project's architecture, add/remove modules, change public APIs, or make significant design decisions, update the relevant `docs/ai/` file:
> - New module or package change -> update `overview.md` if the pipeline changes
> - New design decision or "why" -> append to `decisions.md`
> - New dev workflow or convention -> update `development.md`

### Root Adapter Files

#### `CLAUDE.md`

```markdown
# Memorial Card Digitizer

Read `docs/ai/overview.md` for what this project does.

## Quick Reference
- Run: `./run.sh` or `.venv/bin/python src/main.py`
- Test: `.venv/bin/python -m pytest tests/`
- Always use `.venv/bin/python`, never global Python

## Knowledge Base
Detailed project knowledge lives in `docs/ai/`:
- `architecture.md` — module map and dependencies (auto-generated)
- `api-surface.md` — public functions per package (auto-generated)
- `data-model.md` — schema and file conventions (auto-generated)
- `development.md` — how to run, test, extend
- `decisions.md` — why things are the way they are

Read the relevant file before modifying that area of the codebase.

## Maintenance
When you change architecture, public APIs, or make design decisions,
update the corresponding hand-written file in docs/ai/.
Auto-generated files are rebuilt automatically via hooks.
```

#### `AGENTS.md`

Same content structure as `CLAUDE.md` but without Claude Code-specific hook references. Generic instructions for any AI coding assistant to find and use the knowledge base.

## Out of Scope

- Embedding-based search or vector databases: markdown is sufficient at this project's scale.
- CI/CD integration: the rebuild script is local-only for now.
- Version history of knowledge base files: git handles this.
- Auto-generating `decisions.md` from specs: the value is in human curation of what matters.
- Generating documentation for the `tests/` directory.

## Implementation Notes

- `rebuild.py` should be runnable standalone with no dependencies beyond stdlib.
- The script should gracefully handle missing files or empty packages.
- Auto-generated files should include enough context to be useful standalone (not just function names, but parameter types and brief descriptions).
- The hook should not block the AI session: `--quiet` keeps output minimal and the script should complete in under 1 second for this codebase size.
