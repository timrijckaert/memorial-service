# Memorial Service: Bugfixes and Improvements

## Overview

Eight issues reported by the user, spanning UI feedback, LLM prompt compliance, state persistence, dead code, and git hygiene.

## Issue 1: Title Case for Names

**Problem:** Names extracted by the LLM are stored as-is. No normalization to title case.

**Solution:** Apply `str.title()` to `first_name` and `last_name` in `save_card()` (`src/review/cards.py`) before writing to disk. Also add a title-case instruction to the LLM system prompt so initial extractions are cleaner.

**Files:**
- `src/review/cards.py` — normalize in `save_card()`
- `prompts/extract_person_system.txt` — add "Return names in title case" to OUTPUT FIELDS

**Edge cases:** Dutch name prefixes like "van", "de", "van den" should stay lowercase. `str.title()` will capitalize these incorrectly (e.g., "Van Den Bruelle"). Use a custom title-case function that keeps known Dutch prefixes lowercase when they appear mid-name. The prefix list: `van`, `de`, `den`, `der`, `het`, `ten`, `ter`, `vd`. First word of last_name is always capitalized (e.g., "Van Den Bruelle" stays as-is because "Van" starts the last name).

Actually, re-examining: for Belgian naming conventions the last name IS typically written with capital prefixes (e.g., "Van Cauwenbergh", "Van den Bruelle"). Python's `str.title()` handles this correctly. The only issue is particles like "d'" but those don't appear in the dataset. Use `str.title()` directly.

## Issue 2: "Saved!" Button Feedback

**Problem:** After clicking "Approve", the button turns green and shows "Saved!". If the user then edits a field and clicks again, the button is already green — no visual confirmation that the new save happened.

**Solution:** Two changes in `src/web/static/app.js`:
1. Add `oninput` event listeners on all form fields (name, date, place inputs + spouse inputs) that reset the button back to blue "Approve" whenever any field changes after a save.
2. This makes the flow: Edit -> button shows "Approve" (blue) -> click -> button shows "Saved!" (green) -> edit again -> button resets to "Approve" (blue).

**Files:**
- `src/web/static/app.js` — add a `markFormDirty()` function called by `oninput` on all review form fields, and wire it into `loadReviewCard()` setup and `addSpouseInput()`.

## Issue 3: Age at Death — Two-Part Fix (LLM + Review UI)

**Problem:** The LLM calculates age from dates instead of extracting it from the card text. The user wants the LLM to only extract explicitly stated ages, and the review UI to auto-calculate age when both dates are present.

**Solution — Part A (LLM prompt):** Rewrite the age_at_death instruction to be stronger and clearer:
- Move it into its own dedicated section with a header
- Use explicit "DO NOT" language
- Reframe: "Extract age_at_death ONLY if the card explicitly states the age (e.g., 'in den ouderdom van 78 jaren'). NEVER calculate it from birth and death dates. If the age is not explicitly written on the card, set age_at_death to null."
- Add an example showing both dates present + age null

**Solution — Part B (Review UI auto-calculation):** Add dynamic age calculation in the review tab:
- When both `birth_date` and `death_date` fields have valid dates, auto-calculate the age using plain JS date math and display it in the `age_at_death` field
- Wire this to `oninput` on both date fields so it updates as the user types
- Make the `age_at_death` field read-only when both dates are present (it's computed)
- If only one date is present, the field remains editable (for the LLM-extracted value)
- Calculation: full years between birth and death (account for month/day, not just year subtraction)

**Files:**
- `prompts/extract_person_system.txt` — rewrite age_at_death section
- `src/web/static/app.js` — add `computeAge()` function, wire to date field `oninput` events, toggle read-only state

## Issue 4: Place Name Correction (Haeltert -> Haaltert)

**Problem:** The OCR misspelling correction list already includes `Haeltert -> Haaltert` (line 104), but the LLM sometimes fails to apply it.

**Solution:** Strengthen the normalization instruction. Currently line 20 says "Normalize place names to their modern Dutch spelling using the known places list below." Add a more forceful instruction near the OCR misspellings section: "You MUST apply every correction in this list. If the OCR text contains any of the left-hand spellings, replace with the right-hand spelling."

**Files:**
- `prompts/extract_person_system.txt` — strengthen place normalization instruction

## Issue 5: Deceased Name Appearing as Spouse

**Problem:** The LLM occasionally puts the deceased person's own name in the spouses list.

**Solution:** Add an explicit rule to the prompt: "The deceased's own name must NEVER appear in the spouses list. The spouses list contains only the names of people the deceased was married to."

**Files:**
- `prompts/extract_person_system.txt` — add rule to spouse extraction section

## Issue 6: State Not Persisted on Restart

**Problem:** `MatchState` is purely in-memory. On restart, match and extract phases are blank. The review tab lists all JSON files but skeleton-only cards (not yet extracted) show empty fields.

**Solution:** Reconstruct match state from existing `output/json/*.json` files on startup.

**Implementation:**
1. Add a `restore()` method to `MatchState` that:
   - Scans all `output/json/*.json` files
   - Reads each JSON's `source.front_image_file` and `source.back_image_file`
   - Checks that the source images still exist in `input/`
   - Rebuilds pairs as `auto_confirmed` with their existing `card_id` (the UUID stem)
   - Singles (where `back_image_file` is null) are restored as singles
   - The extract tab can detect which cards already have `person` data via the existing JSON check
2. Call `restore()` at server startup (in `make_server()`), before any requests are handled
3. `scan()` should be aware of already-restored cards — skip images that are already part of a restored pair/single, so re-scanning adds only new images

**Files:**
- `src/web/match_state.py` — add `restore()` method
- `src/main.py` or `src/web/server.py` — call `restore()` at startup in `make_server()`

**Behavior after fix:**
- Start app -> match tab shows previously confirmed pairs -> extract tab shows previous extractions with done/pending status -> review tab shows all cards with person data pre-filled
- Adding new images to `input/` and clicking "Scan" picks up only the new ones

## Issue 7: Remove Redundant Match-Phase Stitching

**Problem:** `match_state.py` stitches images at match confirmation time, writing intermediate files like `output/Scan24.jpeg`. These files are never used — the frontend serves images from `input/` directly, and export does its own stitching to `output/export/`.

**Solution:** Remove `stitch_pair` calls from `MatchState.confirm()` and `MatchState.confirm_all()`. Remove the unused `stitch_pair` import from `match_state.py` and `server.py`.

**Files:**
- `src/web/match_state.py` — remove stitch calls and import
- `src/web/server.py` — remove unused `stitch_pair` import

## Issue 8: Untrack Input Folder from Git

**Problem:** `input/` is in `.gitignore` but the files were committed before the rule was added. Git still tracks them.

**Solution:** Run `git rm --cached -r input/` to untrack without deleting local files. Commit the change.

**Files:**
- Git index only — no code changes

## Summary of Files Changed

| File | Issues |
|------|--------|
| `src/review/cards.py` | 1 (title case) |
| `src/web/static/app.js` | 2 (saved feedback), 3B (age auto-calc) |
| `prompts/extract_person_system.txt` | 3, 4, 5 (LLM prompt) |
| `src/web/match_state.py` | 6 (restore), 7 (remove stitch) |
| `src/main.py` or `src/web/server.py` | 6 (call restore at startup) |
| `src/web/server.py` | 7 (remove unused import) |
| Git index | 8 (untrack input/) |

## Testing Strategy

- **Issue 1:** Unit test `save_card()` with mixed-case names, verify title case in output
- **Issue 2:** Manual test — edit field after save, verify button resets to blue
- **Issue 3-5:** Run extraction on a test card and verify prompt compliance (manual)
- **Issue 6:** Unit test `restore()` — create skeleton/extracted JSONs, verify state reconstruction. Integration test: start server, verify match/extract/review tabs show restored data
- **Issue 7:** Verify no files written to `output/` root during match confirmation
- **Issue 8:** Verify `git ls-files input/` returns empty after fix
