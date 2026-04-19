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

**Tie-break rule:** When a place string contains multiple known localities (e.g. `"Denderhoutem (Haaltert)"`), the match with the **earliest position** in the string wins. In this example, "Denderhoutem" starts at index 0, "Haaltert" at index 15, so "Denderhoutem" is returned.

### Persisted field: `person.locality`

A new non-nullable string field on the person object. Computed at extraction time and persisted in the card JSON. Editable via a dropdown in the Review page. Always one of the four known localities.

Not added to `PERSON_SCHEMA` in `src/extraction/schema.py` — that schema defines the LLM output contract, and locality is computed post-LLM. The field is documented in the persisted data model (`docs/ai/data-model.md`).

### Integration points

**LLM interpretation** (`src/extraction/interpretation.py:57-74`):
- After title-casing and before writing the JSON to disk, call `derive_locality(existing)` and set `existing["person"]["locality"]`. This is the shared persistence path used by both `pipeline.py` (CLI) and `worker.py` (web UI), so all extraction flows get locality populated.

**Filename derivation** (`src/naming.py`):
- `derive_filename()` uses `person.get("locality")` instead of `person.get("birth_place")`.

**Review page frontend** (`index.html` + `app.js`):
- Add a `<select id="f-locality">` dropdown with four options (Haaltert, Kerksken, Denderhoutem, Terjoden).
- Placed in the form between the death_place and age_at_death fields.
- On card load, set the dropdown to `person.locality`.
- Changing `birth_place` or `death_place` always re-derives and updates the locality dropdown value. The user can then override by selecting manually afterwards.
- `computeDerivedName()` uses the locality dropdown value instead of `birth_place`.
- `approveCard()` includes `locality` in the saved payload.

**Backend** (`server.py`):
- No changes needed — `locality` is part of `person` and flows through existing GET/PUT endpoints.

**Data model docs** (`docs/ai/data-model.md`):
- Add `locality` as a non-nullable string field to the documented `PERSON_SCHEMA` shape (the persisted shape, not the LLM output schema).

### Tests

**New: `tests/test_locality.py`**
- Exact match on death_place (e.g. `"Kerksken"` -> `"Kerksken"`)
- Substring match on death_place (e.g. `"Denderhoutem (Haaltert)"` -> `"Denderhoutem"`, earliest position wins)
- Fallback to birth_place when death_place doesn't match
- Default to `"Haaltert"` when neither matches
- Case-insensitive matching

**Updated: `tests/test_naming.py`**
- Filename tests use `locality` instead of `birth_place`.
