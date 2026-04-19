# Locality-based Filename Design

## Problem

The output filename currently uses `birth_place` as the locality component:
`{last_name} {first_name} {birth_place} bidprentje {DD month YYYY}`

This should instead use a derived locality based on the place of death, with fallback to place of birth, constrained to four known localities: Haaltert, Kerksken, Denderhoutem, Terjoden.

## Design

### New module: `src/locality.py`

Exports:
- `KNOWN_LOCALITIES = ["Haaltert", "Kerksken", "Denderhoutem", "Terjoden"]`
- `DEFAULT_LOCALITY = "Haaltert"`
- `derive_locality(card: dict) -> str`

`derive_locality` resolves the locality by:
1. Checking `person.death_place` — if it contains any known locality (case-insensitive substring match), return that locality.
2. Else checking `person.birth_place` — same logic.
3. Else return `"Haaltert"`.

### Persisted field: `person.locality`

A new string field on the person object. Computed at extraction time and persisted in the card JSON. Editable via a dropdown in the Review page.

No backwards compatibility handling — cards without `locality` simply won't have it until re-extracted or manually reviewed.

### Integration points

**Extraction pipeline** (`src/extraction/pipeline.py`):
- After the LLM populates `person`, call `derive_locality(card)` and set `person["locality"]`.

**Filename derivation** (`src/naming.py`):
- `derive_filename()` uses `person.get("locality")` instead of `person.get("birth_place")`.

**Review page frontend** (`index.html` + `app.js`):
- Add a `<select id="f-locality">` dropdown with four options (Haaltert, Kerksken, Denderhoutem, Terjoden).
- Placed in the form between the death_place and age_at_death fields.
- On card load, set the dropdown to `person.locality`.
- Changing `birth_place` or `death_place` re-derives the locality dropdown value, but the user can override by selecting manually.
- `computeDerivedName()` uses the locality dropdown value instead of `birth_place`.
- `approveCard()` includes `locality` in the saved payload.

**Backend** (`server.py`):
- No changes needed — `locality` is part of `person` and flows through existing GET/PUT endpoints.

### Tests

**New: `tests/test_locality.py`**
- Exact match on death_place (e.g. `"Kerksken"` -> `"Kerksken"`)
- Substring match on death_place (e.g. `"Denderhoutem (Haaltert)"` -> `"Denderhoutem"`)
- Fallback to birth_place when death_place doesn't match
- Default to `"Haaltert"` when neither matches
- Case-insensitive matching

**Updated: `tests/test_naming.py`**
- Filename tests use `locality` instead of `birth_place`.
