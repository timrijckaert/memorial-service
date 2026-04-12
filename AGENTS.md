# Memorial Card Digitizer — Agent Instructions

Read `docs/ai/overview.md` for what this project does.

## Quick Reference
- Run: `./run.sh` or `.venv/bin/python -m src.main`
- Test: `.venv/bin/python -m pytest tests/ -v`
- Always use `.venv/bin/python`, never global Python

## Knowledge Base
Detailed project knowledge lives in `docs/ai/`:
- `architecture.md` — module map, file tree, HTTP endpoints (auto-generated)
- `api-surface.md` — public functions per package with signatures (auto-generated)
- `data-model.md` — PERSON_SCHEMA, directory layout, JSON lifecycle (auto-generated)
- `development.md` — how to run, test, extend the project
- `decisions.md` — why things are the way they are

Read the relevant file before modifying that area of the codebase.

## Regenerating Auto-Generated Docs
After modifying source code, run:
```bash
.venv/bin/python docs/ai/rebuild.py
```

## Maintenance
When you change architecture, public APIs, or make design decisions,
update the corresponding hand-written file in `docs/ai/`:
- Pipeline or module changes → update `overview.md`
- New design decision or "why" → append to `decisions.md`
- New dev workflow or convention → update `development.md`
