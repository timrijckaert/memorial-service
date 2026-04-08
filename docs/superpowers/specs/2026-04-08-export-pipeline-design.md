# Export Pipeline & Fuzzy Input Design

**Date:** 2026-04-08
**Branch:** feat/async-pipeline

## Problem

1. The input filenames follow a strict convention, so the fuzzy matcher is never truly tested. Real-world scanned files would have messier names.
2. There is no final Export phase. After Review, there's no way to produce clean output — stitched images with canonical names and a consolidated metadata file.
3. During Extract and Review, cards are identified by internal stems (the original messy filename), which is not meaningful to the user.

## Solution

Three changes:

1. **Derived filename function** — a pure utility that computes a canonical display name from card data
2. **Export phase** — a new final pipeline step that writes stitched images + consolidated JSON to `output/`
3. **Fuzzy input filenames** — rename `input/` files to simulate realistic messy scanner output

## Pipeline

```
Match → Extract → Review (optional) → Export
```

No new gating rules. Export is available as soon as at least 1 card has been extracted.

---

## 1. Derived Filename Function

**Location:** `src/naming.py`

**Signature:** `derive_filename(card: dict) -> str`

**Convention:** `Surname Firstname Birthplace bidprentje DD month YYYY`

- Fields are sourced from `card["person"]`: `last_name`, `first_name`, `birth_place`, `death_date`
- Missing/null fields are omitted (no placeholders)
- `death_date` (ISO `YYYY-MM-DD`) is formatted as `DD month YYYY` with Dutch month names
- The word `bidprentje` is always included as a separator between place and date
- Returns the name without file extension

**Examples:**

| Fields present | Result |
|---|---|
| All fields | `Meganck Dominicus Kerksken bidprentje 21 december 1913` |
| No birth_place | `Meganck Dominicus bidprentje 21 december 1913` |
| No death_date | `Meganck Dominicus Kerksken bidprentje` |
| Only last_name | `Meganck bidprentje` |

**Usage points:**
- Extract tab: display derived name on each card once extraction completes
- Review tab: show derived name (updates as user edits fields)
- Export: output filename

### Dutch Month Formatting

A helper `format_dutch_date(iso_date: str) -> str` converts `YYYY-MM-DD` to `DD month YYYY`:

```
01 → januari, 02 → februari, 03 → maart, 04 → april,
05 → mei, 06 → juni, 07 → juli, 08 → augustus,
09 → september, 10 → oktober, 11 → november, 12 → december
```

---

## 2. Export Phase

### Trigger

A button in the top navigation bar, right-aligned, styled as an action button (not a tab). Displays the count of exportable cards: **"Export (N)"**. Enabled when N >= 1 (at least one extracted card exists).

### Backend

**Endpoint:** `POST /api/export`

**Logic:**
1. List all extracted card JSONs from `output/json/`
2. For each card:
   a. Compute derived filename via `derive_filename(card_data)`
   b. Stitch front + back images (reuse existing `stitch_pair` function)
   c. Write stitched image to `output/{derived_filename}.jpeg`
3. Build consolidated JSON — a dict keyed by derived filename
4. Write `output/memorial_cards.json`

**Response:** `{ "exported": N }` (count of cards exported)

### Consolidated JSON Structure

`output/memorial_cards.json`:

```json
{
  "Meganck Dominicus Kerksken bidprentje 21 december 1913": {
    "first_name": "Dominicus",
    "last_name": "Meganck",
    "birth_date": "1913-12-21",
    "birth_place": "Kerksken",
    "death_date": "1980-03-15",
    "death_place": "Haaltert",
    "age_at_death": 66,
    "spouses": ["Maria Van Damme"],
    "notes": ["..."]
  }
}
```

- Keys are derived filenames (without extension)
- Values contain only `person` fields (flattened, no nested `person` key) + `notes`
- No `source` metadata (internal pipeline details excluded)

### Filename Collisions

If two cards derive the same filename (unlikely but possible), append a numeric suffix: `Name bidprentje date (2).jpeg`.

### Output Directory

Writes directly to `output/` alongside existing `output/json/` and `output/text/` subdirectories. The stitched images and `memorial_cards.json` sit at the top level of `output/`.

---

## 3. Extract & Review Tab Updates

### Extract Tab

Once a card finishes extraction, display the **derived filename** as the card's label instead of the internal card ID/filename stem. This gives the user immediate feedback on what was extracted.

### Review Tab

Show the derived filename as the card header. Since it's computed from the current fields, it updates live as the user edits (e.g., correcting a death date immediately changes the displayed name).

---

## 4. Fuzzy Input Filenames

Rename files in `input/` to simulate realistic messy scanner output. `input_backup/` already contains the original files as a safety copy.

### Renaming Strategy

Both front and back of a pair receive the same category of messiness to keep them matchable.

| Category | ~% of pairs | Transformation | Example |
|---|---|---|---|
| Exactly as-is | ~10% | No change | `Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg` |
| Minor | ~30% | Lowercase, abbreviated month, minor typo | `meganck dominicus kerksken 21 dec 1913.jpeg` |
| Moderate | ~30% | Swapped name order, missing location or keyword | `Dominicus Meganck 1913.jpeg` |
| Heavy | ~30% | Scanner-style or minimal info | `scan_047.jpeg`, `IMG_meganck_2024.jpeg` |

### Back Image Suffixes

Instead of always using ` 1`, back images use varied indicators:
- `_back`, `_2`, `(2)`, `_achterkant`, `_b`, ` back`, `_verso`

This tests the back-image detection regex as well.

### Execution

One-time manual renaming (or a helper script). Not part of the runtime pipeline.

---

## Files Changed

| File | Change |
|---|---|
| `src/naming.py` | **New.** `derive_filename()` and `format_dutch_date()` |
| `src/web/server.py` | Add `POST /api/export` endpoint, add export count to card listing |
| `src/web/static/index.html` | Add Export button in nav bar |
| `src/web/static/app.js` | Export button logic, derived name display in Extract/Review tabs |
| `src/web/static/style.css` | Export button styling |
| `input/*.jpeg` | Renamed to fuzzy variants |
| `tests/test_naming.py` | **New.** Tests for derive_filename and format_dutch_date |

---

## Out of Scope

- Export progress bar (single synchronous operation, fast enough)
- Configurable output directory
- Per-card export (always exports all extracted cards)
- Filename editing by user (derived only, not manually overridden)
