# Locality-based Filename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `birth_place` with a derived `locality` field in output filenames, using death_place → birth_place → "Haaltert" fallback, constrained to four known localities.

**Architecture:** New `src/locality.py` module owns the derivation logic and constants. It's called from `src/extraction/interpretation.py` (post-LLM, pre-write) to persist `person.locality`. `src/naming.py` reads `locality` instead of `birth_place`. The Review UI exposes a dropdown for manual override.

**Tech Stack:** Python 3, vanilla JavaScript, no new dependencies.

---

### Task 1: `src/locality.py` — derive_locality function

**Files:**
- Create: `src/locality.py`
- Create: `tests/test_locality.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_locality.py`:

```python
# tests/test_locality.py
from src.locality import derive_locality


def test_exact_match_death_place():
    card = {"person": {"death_place": "Kerksken", "birth_place": "Brussel"}}
    assert derive_locality(card) == "Kerksken"


def test_exact_match_death_place_haaltert():
    card = {"person": {"death_place": "Haaltert", "birth_place": "Gent"}}
    assert derive_locality(card) == "Haaltert"


def test_exact_match_death_place_denderhoutem():
    card = {"person": {"death_place": "Denderhoutem", "birth_place": None}}
    assert derive_locality(card) == "Denderhoutem"


def test_exact_match_death_place_terjoden():
    card = {"person": {"death_place": "Terjoden", "birth_place": None}}
    assert derive_locality(card) == "Terjoden"


def test_substring_match_earliest_position_wins():
    card = {"person": {"death_place": "Denderhoutem (Haaltert)", "birth_place": None}}
    assert derive_locality(card) == "Denderhoutem"


def test_substring_match_haaltert_first_in_string():
    card = {"person": {"death_place": "Haaltert-Denderhoutem", "birth_place": None}}
    assert derive_locality(card) == "Haaltert"


def test_case_insensitive_match():
    card = {"person": {"death_place": "kerksken", "birth_place": None}}
    assert derive_locality(card) == "Kerksken"


def test_fallback_to_birth_place():
    card = {"person": {"death_place": "Brussel", "birth_place": "Terjoden"}}
    assert derive_locality(card) == "Terjoden"


def test_fallback_to_birth_place_substring():
    card = {"person": {"death_place": "Gent", "birth_place": "Denderhoutem (Haaltert)"}}
    assert derive_locality(card) == "Denderhoutem"


def test_default_when_no_match():
    card = {"person": {"death_place": "Brussel", "birth_place": "Gent"}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_both_none():
    card = {"person": {"death_place": None, "birth_place": None}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_person_empty():
    card = {"person": {}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_no_person_key():
    card = {}
    assert derive_locality(card) == "Haaltert"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_locality.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.locality'`

- [ ] **Step 3: Write the implementation**

Create `src/locality.py`:

```python
# src/locality.py
"""Resolve locality from card data for filename derivation."""

KNOWN_LOCALITIES = ["Haaltert", "Kerksken", "Denderhoutem", "Terjoden"]
DEFAULT_LOCALITY = "Haaltert"


def _find_locality(place: str) -> str | None:
    """Find the known locality that appears earliest in the place string.

    Returns the matching locality (properly cased) or None.
    Case-insensitive substring matching with earliest-position tie-break.
    """
    place_lower = place.lower()
    best_match = None
    best_pos = len(place_lower)

    for loc in KNOWN_LOCALITIES:
        pos = place_lower.find(loc.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_match = loc

    return best_match


def derive_locality(card: dict) -> str:
    """Derive locality from death_place, then birth_place, defaulting to Haaltert.

    Checks death_place first, then birth_place. Each is matched against
    the known localities using case-insensitive substring matching.
    If neither matches, returns "Haaltert".
    """
    person = card.get("person", {})

    death_place = person.get("death_place")
    if death_place:
        match = _find_locality(death_place)
        if match:
            return match

    birth_place = person.get("birth_place")
    if birth_place:
        match = _find_locality(birth_place)
        if match:
            return match

    return DEFAULT_LOCALITY
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_locality.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/locality.py tests/test_locality.py
git commit -m "feat: add locality derivation module with known-place matching"
```

---

### Task 2: Integrate locality into extraction pipeline

**Files:**
- Modify: `src/extraction/interpretation.py:56-74`

- [ ] **Step 1: Write the failing test**

There are no unit tests for `interpret_text` (it requires an LLM backend). Instead, verify the integration by reading the existing code and checking the change is structurally correct. The existing integration tests in the project will cover this.

Add a focused test to `tests/test_locality.py` that validates the pattern we'll use in `interpret_text`:

```python
def test_derive_locality_sets_on_card_dict():
    """Verify derive_locality works when called on a full card structure
    matching how interpret_text builds the 'existing' dict."""
    existing = {
        "person": {
            "first_name": "Jan",
            "last_name": "Peeters",
            "birth_place": "Gent",
            "death_place": "Kerksken",
        },
        "notes": [],
        "source": {},
    }
    existing["person"]["locality"] = derive_locality(existing)
    assert existing["person"]["locality"] == "Kerksken"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_locality.py::test_derive_locality_sets_on_card_dict -v`
Expected: PASS (this uses the already-implemented `derive_locality`)

- [ ] **Step 3: Modify `interpret_text` to set locality**

In `src/extraction/interpretation.py`, add the import at the top:

```python
from src.locality import derive_locality
```

Then after the title-casing block (after line 55) and before the "Read existing file" comment (line 57), add:

```python
    # Derive locality for filename
    person["locality"] = derive_locality(result)
```

Note: `person` is already a reference to `result["person"]` from line 48, and `result` has the `person` key from the LLM output. This sets locality on the result dict before it gets merged into `existing`.

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/extraction/interpretation.py tests/test_locality.py
git commit -m "feat: derive locality in interpret_text before persisting card JSON"
```

---

### Task 3: Update `derive_filename` to use locality

**Files:**
- Modify: `src/naming.py:26-31`
- Modify: `tests/test_naming.py`

- [ ] **Step 1: Update tests to use locality instead of birth_place**

Replace the contents of `tests/test_naming.py`:

```python
# tests/test_naming.py
from src.naming import format_dutch_date, derive_filename


def test_format_dutch_date_januari():
    assert format_dutch_date("1913-01-21") == "21 januari 1913"


def test_format_dutch_date_december():
    assert format_dutch_date("1980-12-15") == "15 december 1980"


def test_format_dutch_date_mei():
    assert format_dutch_date("1927-05-04") == "04 mei 1927"


def test_format_dutch_date_strips_leading_zero_not():
    # Convention keeps leading zero: "05 januari" not "5 januari"
    assert format_dutch_date("1898-01-05") == "05 januari 1898"


def test_derive_filename_all_fields():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": "Kerksken",
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje 21 december 1913"


def test_derive_filename_no_locality():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": None,
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus bidprentje 21 december 1913"


def test_derive_filename_no_death_date():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": "Kerksken",
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje"


def test_derive_filename_only_last_name():
    card = {
        "person": {
            "first_name": None,
            "last_name": "Meganck",
            "locality": None,
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck bidprentje"


def test_derive_filename_empty_person():
    card = {"person": {}}
    assert derive_filename(card) == "bidprentje"


def test_derive_filename_missing_person_key():
    card = {}
    assert derive_filename(card) == "bidprentje"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_naming.py -v`
Expected: `test_derive_filename_all_fields` FAILS (still reading `birth_place`)

- [ ] **Step 3: Update `derive_filename` to use locality**

In `src/naming.py`, replace:

```python
    if person.get("birth_place"):
        parts.append(person["birth_place"])
```

with:

```python
    if person.get("locality"):
        parts.append(person["locality"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_naming.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/naming.py tests/test_naming.py
git commit -m "feat: use locality instead of birth_place in derived filename"
```

---

### Task 4: Add locality dropdown to Review UI

**Files:**
- Modify: `src/web/static/index.html:88-89`
- Modify: `src/web/static/app.js:574-616` (loadReviewCard)
- Modify: `src/web/static/app.js:666-693` (approveCard)
- Modify: `src/web/static/app.js:695-719` (computeDerivedName)

- [ ] **Step 1: Add the dropdown HTML**

In `src/web/static/index.html`, after the Death Place form group (line 88) and before the Age at Death form group (line 89), add:

```html
        <div class="form-group"><label>Locality</label><select id="f-locality"><option value="Haaltert">Haaltert</option><option value="Kerksken">Kerksken</option><option value="Denderhoutem">Denderhoutem</option><option value="Terjoden">Terjoden</option></select></div>
```

- [ ] **Step 2: Update `loadReviewCard` to populate the dropdown**

In `src/web/static/app.js`, after the line that sets `f-death_place` (line 580):

```javascript
  document.getElementById('f-death_place').value = p.death_place || '';
```

Add:

```javascript
  document.getElementById('f-locality').value = p.locality || 'Haaltert';
```

Then in the `oninput` wiring section (lines 601-606), change:

```javascript
  ['f-first_name', 'f-last_name', 'f-birth_place', 'f-death_place'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      computeDerivedName();
    };
  });
```

to:

```javascript
  ['f-first_name', 'f-last_name'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      computeDerivedName();
    };
  });
  ['f-birth_place', 'f-death_place'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      deriveLocality();
      computeDerivedName();
    };
  });
  document.getElementById('f-locality').onchange = function() {
    markFormDirty();
    computeDerivedName();
  };
```

- [ ] **Step 3: Add `deriveLocality` function and update `computeDerivedName`**

In `src/web/static/app.js`, add this function before `computeDerivedName` (before line 695):

```javascript
function deriveLocality() {
  var knownLocalities = ['Haaltert', 'Kerksken', 'Denderhoutem', 'Terjoden'];
  var deathPlace = document.getElementById('f-death_place').value.trim().toLowerCase();
  var birthPlace = document.getElementById('f-birth_place').value.trim().toLowerCase();

  function findLocality(place) {
    if (!place) return null;
    var bestMatch = null;
    var bestPos = place.length;
    for (var i = 0; i < knownLocalities.length; i++) {
      var pos = place.indexOf(knownLocalities[i].toLowerCase());
      if (pos !== -1 && pos < bestPos) {
        bestPos = pos;
        bestMatch = knownLocalities[i];
      }
    }
    return bestMatch;
  }

  var result = findLocality(deathPlace) || findLocality(birthPlace) || 'Haaltert';
  document.getElementById('f-locality').value = result;
}
```

Then in `computeDerivedName`, replace:

```javascript
  var birthPlace = document.getElementById('f-birth_place').value.trim();
```

with:

```javascript
  var locality = document.getElementById('f-locality').value;
```

And replace:

```javascript
  if (birthPlace) parts.push(birthPlace);
```

with:

```javascript
  if (locality) parts.push(locality);
```

- [ ] **Step 4: Update `approveCard` to include locality**

In `src/web/static/app.js`, in the `approveCard` function, after the `death_place` line:

```javascript
      death_place: document.getElementById('f-death_place').value.trim() || null,
```

Add:

```javascript
      locality: document.getElementById('f-locality').value,
```

- [ ] **Step 5: Manual test in browser**

Run: `./run.sh`
Open the app, go to the Review tab. Verify:
1. The Locality dropdown appears between Death Place and Age at Death
2. It shows the correct value from the card data
3. Changing Death Place re-derives the dropdown
4. Changing Birth Place re-derives the dropdown (when death place has no match)
5. The derived filename at the top updates when the dropdown changes
6. Saving preserves the locality value

- [ ] **Step 6: Commit**

```bash
git add src/web/static/index.html src/web/static/app.js
git commit -m "feat: add locality dropdown to review UI with auto-derivation"
```

---

### Task 5: Update data model documentation

**Files:**
- Modify: `docs/ai/data-model.md`

The `data-model.md` file is auto-generated by `docs/ai/rebuild.py`, so this will be handled automatically by the PostToolUse hooks when files are modified. No manual action needed — just verify the rebuild picks up the new `locality` field after the implementation tasks are done.

- [ ] **Step 1: Verify data-model.md was auto-rebuilt**

Check that `docs/ai/data-model.md` includes `locality` after the previous tasks triggered a rebuild. If it hasn't updated (because the auto-generated file reads from `PERSON_SCHEMA` which we intentionally didn't modify), manually add `locality` to the documented persisted shape.

In `docs/ai/data-model.md`, after the `death_place` property block, add:

```json
        "locality": {
          "type": "string"
        },
```

And add `"locality"` to the `required` array.

- [ ] **Step 2: Commit if manual change was needed**

```bash
git add docs/ai/data-model.md
git commit -m "docs: add locality field to persisted data model"
```

---

### Task 6: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Commit any remaining changes**

If any fixes were needed, commit them.
