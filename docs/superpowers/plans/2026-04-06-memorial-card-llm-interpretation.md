# Memorial Card LLM Text Interpretation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interpret OCR-extracted text from memorial cards using a local LLM (Ollama + Gemma 4 E2B) to produce structured JSON with biographical data, confidence scores, and notes.

**Architecture:** Adds an `interpret_text` function to `src/merge.py` that sends combined front/back text to Ollama with a structured output schema. The prompt is loaded from an editable file (`prompts/extract_person.txt`). The `main()` loop calls interpretation after OCR. `run.sh` gains Ollama/model checks.

**Tech Stack:** Python 3, Ollama (local LLM runtime), Gemma 4 E2B model, `ollama` Python client

---

## File Structure

- **Modify:** `requirements.txt` — add `ollama>=0.4`
- **Create:** `prompts/extract_person.txt` — editable prompt template with place names and instructions
- **Modify:** `run.sh` — add Ollama availability check and model auto-pull
- **Create:** `tests/test_interpret.py` — tests for `interpret_text` with mocked Ollama
- **Modify:** `src/merge.py` — add `PERSON_SCHEMA` constant, `interpret_text` function, update `main()` to run interpretation per pair

---

### Task 1: Add ollama Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add ollama to requirements.txt**

Edit `requirements.txt` to add the new dependency:

```
Pillow>=10.0
pytest>=8.0
pytesseract>=0.3.10
ollama>=0.4
```

- [ ] **Step 2: Reinstall dependencies in the venv**

Run:
```bash
.venv/bin/pip install -r requirements.txt
```

Expected: Successfully installs `ollama`. Verify with:
```bash
.venv/bin/python -c "import ollama; print('ollama imported OK')"
```

This should print `ollama imported OK`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add ollama dependency for LLM text interpretation"
```

---

### Task 2: Create Prompt Template

**Files:**
- Create: `prompts/extract_person.txt`

- [ ] **Step 1: Create the prompts directory and prompt file**

Create `prompts/extract_person.txt`:

```
You are a genealogy data extraction assistant. Extract biographical information from Belgian memorial cards (bidprentjes). The text was extracted via OCR and may contain errors.

IMPORTANT RULES:
- Both front and back text are provided. Check BOTH for information — names can appear on either side.
- Return dates in ISO 8601 format (YYYY-MM-DD).
- If a birth date is not explicitly stated but death date and age at death are given, deduce the approximate birth date and note this in the notes array.
- Normalize place names to their modern Dutch spelling using the known places list below.
- Confidence is a float from 0.0 to 1.0 for each field. Use lower confidence when you are deducing information or correcting OCR errors. Set confidence to null when the corresponding field is null.
- Add a note whenever you deduce a value, correct an OCR error, or are uncertain about an extraction.
- For spouse: extract the full name as a single string. Set to null if not mentioned.
- For parents: extract father and mother names separately. Set the parents object to null if neither parent is mentioned. Individual parent fields can be null if only one is mentioned.
- For age_at_death: extract as an integer. Set to null if not mentioned and not deducible.

OUTPUT FIELDS:
- first_name: Given/first name(s) of the deceased
- last_name: Family/surname of the deceased
- birth_date: Date of birth in YYYY-MM-DD format
- birth_place: Place of birth (normalized to modern spelling)
- death_date: Date of death in YYYY-MM-DD format
- death_place: Place of death (normalized to modern spelling)
- age_at_death: Age at death as an integer
- spouse: Full name of spouse (husband/wife)
- parents.father: Full name of father
- parents.mother: Full name of mother (often maiden name)
- confidence: 0.0-1.0 score for each field (null if field is null)
- notes: Array of strings explaining deductions, corrections, uncertainties

KNOWN PLACES (Arrondissement Aalst, Oost-Vlaanderen, Belgium):
Haaltert, Denderhoutem, Heldergem, Kerksken, Terjoden, Aalst, Baardegem, Erembodegem, Gijzegem, Herdersem, Hofstade, Meldert, Moorsel, Nieuwerkerken, Denderleeuw, Iddergem, Erpe-Mere, Aaigem, Bambrugge, Burst, Erondegem, Erpe, Mere, Ottergem, Vlekkem, Herzele, Borsbeke, Hillegem, Ressegem, Sint-Antelinks, Sint-Lievens-Esse, Lede, Impe, Oordegem, Smetlede, Wanzele, Ninove, Zottegem, Geraardsbergen, Dendermonde, Welle, Lemberge, Tiedekerk

COMMON OCR MISSPELLINGS:
Haeltert -> Haaltert, Kerkxken -> Kerksken, Haciltert -> Haaltert, Denderhautem -> Denderhoutem, Tiedekérke -> Tiedekerk, Aygem -> Aaigem

--- FRONT TEXT ---
{front_text}

--- BACK TEXT ---
{back_text}
```

- [ ] **Step 2: Commit**

```bash
git add prompts/extract_person.txt
git commit -m "feat: add editable prompt template for LLM text interpretation"
```

---

### Task 3: Update run.sh with Ollama Checks

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Add Ollama and model checks to run.sh**

Add the following after the Dutch language pack download block (after line 29) and before the venv setup block (line 31):

```bash
# Check Ollama is available
if ! command -v ollama &>/dev/null; then
    echo "Error: ollama is required but not found."
    echo "Install it with: brew install ollama"
    exit 1
fi

# Check Ollama service is running
if ! ollama list &>/dev/null; then
    echo "Error: Ollama service is not running."
    echo "Start it with: ollama serve"
    echo "Or open the Ollama app."
    exit 1
fi

# Pull Gemma 4 E2B model if not present
if ! ollama list | grep -q "gemma4:e2b"; then
    echo "Downloading Gemma 4 E2B model for text interpretation..."
    ollama pull gemma4:e2b
    echo "Model downloaded."
    echo ""
fi
```

The full `run.sh` after this change:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Check Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew: brew install python3"
    exit 1
fi

# Check Tesseract is available
if ! command -v tesseract &>/dev/null; then
    echo "Error: tesseract is required but not found."
    echo "Install it with: brew install tesseract"
    exit 1
fi

# Download Dutch language pack if missing
TESSDATA_DIR="$(dirname "$(command -v tesseract)")/../share/tessdata"
if [ ! -f "$TESSDATA_DIR/nld.traineddata" ]; then
    echo "Downloading Dutch language pack for Tesseract..."
    curl -sL -o "$TESSDATA_DIR/nld.traineddata" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/nld.traineddata
    echo "Dutch language pack installed."
    echo ""
fi

# Check Ollama is available
if ! command -v ollama &>/dev/null; then
    echo "Error: ollama is required but not found."
    echo "Install it with: brew install ollama"
    exit 1
fi

# Check Ollama service is running
if ! ollama list &>/dev/null; then
    echo "Error: Ollama service is not running."
    echo "Start it with: ollama serve"
    echo "Or open the Ollama app."
    exit 1
fi

# Pull Gemma 4 E2B model if not present
if ! ollama list | grep -q "gemma4:e2b"; then
    echo "Downloading Gemma 4 E2B model for text interpretation..."
    ollama pull gemma4:e2b
    echo "Model downloaded."
    echo ""
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Run the merge script
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/merge.py"
```

- [ ] **Step 2: Verify the check works**

Run:
```bash
bash run.sh
```

Expected: If Ollama is installed and running with the model, the script runs normally. If Ollama is not installed, it prints install instructions and exits.

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "feat: add ollama availability and model checks to run.sh"
```

---

### Task 4: Write LLM Interpretation Tests

**Files:**
- Create: `tests/test_interpret.py`

These tests mock the Ollama client so they run without Ollama installed.

- [ ] **Step 1: Write the test file with five tests**

Create `tests/test_interpret.py`:

```python
# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.merge import interpret_text


SAMPLE_LLM_RESPONSE = json.dumps({
    "person": {
        "first_name": "Dominicus",
        "last_name": "Meganck",
        "birth_date": "1813-12-18",
        "birth_place": "Kerksken",
        "death_date": "1913-12-21",
        "death_place": "Kerksken",
        "age_at_death": 100,
        "spouse": "Amelia Gees",
        "parents": None
    },
    "confidence": {
        "first_name": 0.95,
        "last_name": 0.95,
        "birth_date": 0.9,
        "birth_place": 0.9,
        "death_date": 0.95,
        "death_place": 0.85,
        "age_at_death": 0.95,
        "spouse": 0.9,
        "parents": None
    },
    "notes": [
        "birth_place OCR reads 'Kerkxken', normalized to 'Kerksken'"
    ]
})

PROMPT_TEMPLATE = (
    "Extract info.\n\n--- FRONT TEXT ---\n{front_text}\n\n--- BACK TEXT ---\n{back_text}"
)


def _mock_chat_response(content: str):
    """Create a mock ollama ChatResponse."""
    mock_response = MagicMock()
    mock_response.message.content = content
    return mock_response


@patch("src.merge.ollama.chat")
def test_interpret_text_creates_json_file(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Some front text")
    back_text.write_text("Dominicus Meganck geboren 1813")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    assert output.exists()


@patch("src.merge.ollama.chat")
def test_interpret_text_json_has_required_keys(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("Test text")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    result = json.loads(output.read_text())
    assert "person" in result
    assert "confidence" in result
    assert "notes" in result
    assert "source" in result


@patch("src.merge.ollama.chat")
def test_interpret_text_includes_source_filenames(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    result = json.loads(output.read_text())
    assert result["source"]["front_text_file"] == "card_front.txt"
    assert result["source"]["back_text_file"] == "card 1_back.txt"


@patch("src.merge.ollama.chat")
def test_interpret_text_substitutes_placeholders(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response(SAMPLE_LLM_RESPONSE)

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("Voorkant tekst")
    back_text.write_text("Achterkant tekst")
    output = tmp_path / "card.json"

    interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)

    call_args = mock_chat.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert "Voorkant tekst" in prompt
    assert "Achterkant tekst" in prompt
    assert "{front_text}" not in prompt
    assert "{back_text}" not in prompt


@patch("src.merge.ollama.chat")
def test_interpret_text_invalid_json_raises(mock_chat, tmp_path):
    mock_chat.return_value = _mock_chat_response("not valid json at all")

    front_text = tmp_path / "card_front.txt"
    back_text = tmp_path / "card 1_back.txt"
    front_text.write_text("")
    back_text.write_text("")
    output = tmp_path / "card.json"

    with pytest.raises(json.JSONDecodeError):
        interpret_text(front_text, back_text, output, PROMPT_TEMPLATE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_interpret.py -v
```

Expected: All 5 tests FAIL with `ImportError: cannot import name 'interpret_text' from 'src.merge'` (the function doesn't exist yet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_interpret.py
git commit -m "test: add LLM interpretation tests with mocked Ollama"
```

---

### Task 5: Implement interpret_text Function

**Files:**
- Modify: `src/merge.py:1-4` (imports) and add function + constant after `extract_text`

- [ ] **Step 1: Add ollama and json imports to src/merge.py**

Update the imports at the top of `src/merge.py` from:

```python
# src/merge.py
from pathlib import Path
from PIL import Image
import pytesseract
```

to:

```python
# src/merge.py
import json
from pathlib import Path
from PIL import Image
import ollama
import pytesseract
```

- [ ] **Step 2: Add PERSON_SCHEMA constant and interpret_text function after extract_text**

Add this after the `extract_text` function (after line 101) and before `main()`:

```python
PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "first_name": {"type": ["string", "null"]},
                "last_name": {"type": ["string", "null"]},
                "birth_date": {"type": ["string", "null"]},
                "birth_place": {"type": ["string", "null"]},
                "death_date": {"type": ["string", "null"]},
                "death_place": {"type": ["string", "null"]},
                "age_at_death": {"type": ["integer", "null"]},
                "spouse": {"type": ["string", "null"]},
                "parents": {
                    "type": ["object", "null"],
                    "properties": {
                        "father": {"type": ["string", "null"]},
                        "mother": {"type": ["string", "null"]},
                    },
                },
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouse", "parents",
            ],
        },
        "confidence": {
            "type": "object",
            "properties": {
                "first_name": {"type": ["number", "null"]},
                "last_name": {"type": ["number", "null"]},
                "birth_date": {"type": ["number", "null"]},
                "birth_place": {"type": ["number", "null"]},
                "death_date": {"type": ["number", "null"]},
                "death_place": {"type": ["number", "null"]},
                "age_at_death": {"type": ["number", "null"]},
                "spouse": {"type": ["number", "null"]},
                "parents": {"type": ["number", "null"]},
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouse", "parents",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "confidence", "notes"],
}

MODEL = "gemma4:e2b"


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    prompt_template: str,
) -> None:
    """Interpret OCR text using a local LLM and write structured JSON.

    Reads front and back text files, substitutes them into the prompt template,
    sends to Ollama (Gemma 4 E2B) with a structured output schema, and writes
    the parsed JSON to output_path. Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    prompt = prompt_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=PERSON_SCHEMA,
        options={"temperature": 0},
    )

    result = json.loads(response.message.content)

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 3: Run interpretation tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_interpret.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 4: Run full test suite to verify nothing broke**

Run:
```bash
.venv/bin/python -m pytest -v
```

Expected: All 20 tests PASS (7 pairing + 5 stitching + 3 OCR + 5 interpretation).

- [ ] **Step 5: Commit**

```bash
git add src/merge.py
git commit -m "feat: implement LLM text interpretation with Ollama"
```

---

### Task 6: Integrate Interpretation into Main Pipeline

**Files:**
- Modify: `src/merge.py:104-171` (the `main()` function)

- [ ] **Step 1: Update main() to load prompt, check Ollama, create json dir, and run interpretation**

Replace the entire `main()` function in `src/merge.py` with:

```python
def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    text_dir = output_dir / "text"
    json_dir = output_dir / "json"
    prompt_path = script_dir / "prompts" / "extract_person.txt"

    if not input_dir.exists():
        input_dir.mkdir()
        print(f"Created {input_dir}/ — drop your scans there and run again.")
        return

    pairs, errors = find_pairs(input_dir)

    if not pairs and not errors:
        print("No scans found in input/. Drop front + back JPEG pairs there and run again.")
        return

    output_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)
    json_dir.mkdir(exist_ok=True)

    # Load prompt template
    prompt_template = None
    if prompt_path.exists():
        prompt_template = prompt_path.read_text()
    else:
        print(f"Warning: prompt template not found at {prompt_path} — skipping interpretation")

    # Pre-flight check: is Ollama reachable?
    ollama_available = False
    if prompt_template:
        try:
            ollama.list()
            ollama_available = True
        except Exception:
            print("Warning: Ollama not reachable — skipping text interpretation")

    total = len(pairs)
    ok_count = 0
    text_count = 0
    interpret_count = 0
    width = len(str(total))

    print(f"Found {len(pairs)} pair{'s' if len(pairs) != 1 else ''} in input/")

    all_errors: list[str] = list(errors)

    for i, (front_path, back_path) in enumerate(pairs, 1):
        output_path = output_dir / front_path.name
        pair_ok = True

        # Stitch
        try:
            stitch_pair(front_path, back_path, output_path)
            ok_count += 1
        except Exception as e:
            all_errors.append(f"{front_path.name} stitch: {e}")
            pair_ok = False

        # OCR
        front_text_path = text_dir / f"{front_path.stem}_front.txt"
        back_text_path = text_dir / f"{back_path.stem}_back.txt"
        try:
            extract_text(front_path, front_text_path)
            extract_text(back_path, back_text_path)
            text_count += 1
        except Exception as e:
            all_errors.append(f"{front_path.name} OCR: {e}")
            pair_ok = False

        # LLM Interpretation
        if ollama_available:
            json_output_path = json_dir / f"{front_path.stem}.json"
            try:
                interpret_text(front_text_path, back_text_path, json_output_path, prompt_template)
                interpret_count += 1
            except Exception as e:
                all_errors.append(f"{front_path.name} interpret: {e}")
                pair_ok = False

        # Progress
        if pair_ok:
            print(f"[{i:>{width}}/{total}] {front_path.name}  OK")
        else:
            print(f"[{i:>{width}}/{total}] {front_path.name}  ERROR")

    print(f"\nDone: {ok_count} merged, {text_count} text extracted, {interpret_count} interpreted, {len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    if all_errors:
        print(f"\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")
```

- [ ] **Step 2: Run the full test suite**

Run:
```bash
.venv/bin/python -m pytest -v
```

Expected: All 20 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/merge.py
git commit -m "feat: integrate LLM interpretation into main pipeline"
```

---

### Task 7: Manual Verification

- [ ] **Step 1: Ensure Ollama is running with the model**

Run:
```bash
ollama list | grep gemma4:e2b
```

If not present, run:
```bash
ollama pull gemma4:e2b
```

- [ ] **Step 2: Run the full pipeline on real scans**

Run:
```bash
.venv/bin/python src/merge.py
```

Expected output similar to:
```
Found 21 pairs in input/
[ 1/21] Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg  OK
...

Done: 21 merged, 21 text extracted, 21 interpreted, 0 errors
```

Note: The first run will be slower as the model loads into memory. Subsequent cards process faster.

- [ ] **Step 3: Verify JSON output files exist**

Run:
```bash
ls output/json/ | head -5
```

Expected: JSON files named after the front scans with `.json` extension.

- [ ] **Step 4: Inspect a JSON file for quality**

Run:
```bash
cat "output/json/$(ls output/json/ | head -1)"
```

Expected: Valid JSON with `person`, `confidence`, `notes`, and `source` sections. Check that:
- Names are extracted correctly
- Dates are in ISO 8601 format (YYYY-MM-DD)
- Place names are normalized to modern spelling
- Confidence scores are reasonable (0.0–1.0)
- Notes explain any deductions or corrections

- [ ] **Step 5: Commit any final adjustments**

If the prompt template needs tweaking based on results:
```bash
git add prompts/extract_person.txt
git commit -m "chore: tune prompt template after manual verification"
```

If everything looks good with no changes, no commit needed.
