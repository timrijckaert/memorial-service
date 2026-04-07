# Split merge and extraction into separate concerns

## Problem

`src/merge.py` is a single 450-line file that handles image stitching (fast) and metadata extraction via OCR + LLM (slow). They cannot be run independently, and re-runs redo all work from scratch.

## Design

Split into three modules with a CLI entry point supporting subcommands.

### Module structure

**`src/main.py`** --- CLI entry point

- Parses subcommands via `argparse`: `merge`, `extract`, `all` (default)
- Accepts `--force` flag to skip the "already done" check
- Calls `find_pairs()` from `merge` module
- Delegates to `merge_all()` and/or `extract_all()`
- Owns all console output (progress, summary, errors)

**`src/merge.py`** --- Image pairing and stitching

- `find_pairs(input_dir) -> (pairs, errors)` --- unchanged
- `stitch_pair(front, back, output) -> None` --- unchanged
- `merge_all(pairs, output_dir, force=False) -> (ok_count, skipped, errors)` --- new orchestrator that loops pairs, applies skip logic, calls `stitch_pair`

**`src/extract.py`** --- OCR and LLM metadata extraction

- `_clean_ocr_text(raw) -> str` --- moved from merge.py
- `extract_text(image, output) -> None` --- moved from merge.py
- `verify_dates(image, text, conflicts_dir) -> list[str]` --- moved from merge.py
- `interpret_text(front_text, back_text, output, template) -> None` --- moved from merge.py
- `PERSON_SCHEMA`, `MODEL`, `_YEAR_RE` --- moved here
- `extract_all(pairs, text_dir, json_dir, conflicts_dir, prompt_template, force=False) -> (text_count, verify_count, interpret_count, errors)` --- new orchestrator, parallel via `ThreadPoolExecutor`

### CLI interface

```
python src/main.py              # runs merge then extract (default: "all")
python src/main.py merge        # stitch only
python src/main.py extract      # OCR + dates + LLM only
python src/main.py all --force  # redo everything
```

`run.sh` changes one line: invokes `src/main.py` instead of `src/merge.py`.

### Skip-if-done logic

- **merge phase**: skip pair if `output/{front_name}` exists
- **extract phase**: skip pair if `output/json/{front_stem}.json` exists
- **`--force`**: ignore existing files, process everything

### Progress output

```
Found 27 pairs in input/
Skipping 20 already merged

[1/7] New card A  OK
[2/7] New card B  OK
...

Done: 7 merged (20 skipped), 7 text extracted, 2 dates corrected, 7 interpreted, 0 errors
```

### Test changes

**No changes needed:**
- `test_pairing.py` --- imports `from src.merge import find_pairs` (stays in merge.py)
- `test_stitching.py` --- imports `from src.merge import stitch_pair` (stays in merge.py)

**Import update needed:**
- `test_ocr.py` --- change `from src.merge import extract_text` to `from src.extract import extract_text`
- `test_interpret.py` --- change `from src.merge import interpret_text` to `from src.extract import interpret_text`, update 5 `@patch("src.merge.ollama.chat")` to `@patch("src.extract.ollama.chat")`
- `test_verify_dates.py` --- change `from src.merge import verify_dates` to `from src.extract import verify_dates`, update 7 `@patch("src.merge.ollama.chat")` to `@patch("src.extract.ollama.chat")`, update 7 `@patch("src.merge.pytesseract.image_to_data")` to `@patch("src.extract.pytesseract.image_to_data")`

**No new tests** needed for `merge_all`/`extract_all` (thin orchestrators calling already-tested functions)

### Constraints

- No new dependencies
- Existing function signatures unchanged (only move between files)
- `run.sh` only changes the python invocation line
