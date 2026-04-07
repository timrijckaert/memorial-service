# Multiple Spouses Support

## Problem

The current data model uses `"spouse": string | null` which can only store one spouse name. Belgian memorial cards sometimes mention multiple marriages (e.g., "weduwe in 't 1e huwelijk van X, in 't 2e huwelijk van Y"). The second (and subsequent) spouses are lost — they end up in the `notes` array as unstructured text.

Example: Rosalie Van Schandevijl married Desire de Clercq (1st) and Jan-Baptist Roelandt (2nd). Only the first spouse is captured in the `spouse` field.

## Design

Rename `spouse` to `spouses` and change the type from `string | null` to `array of strings`.

- Empty list `[]` when no spouse is known
- Single-element list `["Desire de Clercq"]` for one marriage
- Multi-element list `["Desire de Clercq", "Jan-Baptist Roelandt"]` for multiple marriages
- Order in the list matches marriage order (1st marriage first)

No additional metadata per spouse (no order number, no deceased flag). Just names.

## Changes

### 1. JSON Schema (`src/extract.py`)

In `PERSON_SCHEMA`, replace:

```python
"spouse": {"type": ["string", "null"]},
```

with:

```python
"spouses": {"type": "array", "items": {"type": "string"}},
```

Update the `required` list: replace `"spouse"` with `"spouses"`.

### 2. Extraction Prompt (`prompts/extract_person.txt`)

Update the prompt to:

- Change the `spouse` output field description to `spouses` (array of strings)
- Instruct the LLM to list all spouse names in marriage order
- Remove the instruction that puts extra marriages in `notes`
- Keep the existing Dutch keyword rules (echtgenoot van, weduwe van, etc.) — they still apply, just collect all matches into the array

### 3. Review UI (`src/review.py`)

Replace the single `<input id="f-spouse">` with a dynamic list UI:

- Display each spouse as a text input with a remove button
- Add an "Add spouse" button to append a new empty input
- On load: read `person.spouses` array, create one input per entry
- On save: collect all non-empty spouse inputs into the `spouses` array

### 4. Tests

**`tests/test_interpret.py`:**
- Update `SAMPLE_LLM_RESPONSE` to use `"spouses": ["Amelia Gees"]` instead of `"spouse": "Amelia Gees"`

**`tests/test_review.py`:**
- No structural changes needed — tests don't assert on spouse field contents

## Out of Scope

- Migration of existing JSON files in `output/json/` — existing files keep the old `spouse` field
- Marriage metadata (order numbers, deceased status)
- Backwards compatibility layer
