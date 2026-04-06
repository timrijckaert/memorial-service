# Memorial Card LLM Text Interpretation — Design Spec

## Problem

The memorial card processor already extracts raw OCR text from front and back scans (Phase 3). The extracted text is unstructured Dutch prose with OCR artifacts. We need to interpret this text and extract structured biographical data into a standardized JSON format for each deceased person, enabling searching, indexing, and genealogical research.

## Constraints

- macOS (Apple Silicon or Intel), 16GB RAM MacBook Air
- Ollama installed locally — no cloud APIs, no API keys
- Model: Gemma 4 E2B (~2.3B effective params, ~7GB download) — fits comfortably on 16GB
- `run.sh` checks for Ollama and the model, auto-pulls if missing
- Editable prompt file so the user can tune LLM behavior without code changes
- LLM interpretation must never crash the pipeline — errors are logged and processing continues

## Dependencies

### System

- `ollama` — local LLM runtime (installed via `brew install ollama`)
- `gemma4:e2b` model — auto-pulled by `run.sh` if not present

### Python

- `ollama` — official Python client for Ollama (added to `requirements.txt`)

## JSON Output Schema

Each card pair produces one JSON file:

```json
{
  "source": {
    "front_text_file": "Name_front.txt",
    "back_text_file": "Name 1_back.txt"
  },
  "person": {
    "first_name": "Dominicus",
    "last_name": "Meganck",
    "birth_date": "1813-12-18",
    "birth_place": "Kerksken",
    "death_date": "1913-12-21",
    "death_place": "Kerksken",
    "age_at_death": 100,
    "spouse": "Amelia Gees",
    "parents": {
      "father": "Ludovicus Meganck",
      "mother": "Joanna Redant"
    }
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
    "parents": 0.85
  },
  "notes": [
    "birth_date deduced from death_date (21 Dec 1913) minus age (100 years)",
    "birth_place OCR reads 'Kerkxken', normalized to 'Kerksken'"
  ]
}
```

### Field Rules

- **Dates:** ISO 8601 format (`YYYY-MM-DD`)
- **Confidence:** 0.0–1.0 per field. `null` when the field itself is `null`
- **`spouse`:** Full name string, `null` if not mentioned
- **`parents`:** Object with `father` and `mother` keys (each a string or `null`), `null` if neither parent is mentioned
- **`age_at_death`:** Integer, `null` if not mentioned or deducible
- **Notes:** Array of strings explaining deductions, OCR corrections, or uncertainties
- **Deduction:** If birth date is not explicit but death date and age are given, the LLM should deduce it and note this in `notes`

## Interpretation Function

**`interpret_text(front_text_path: Path, back_text_path: Path, output_path: Path, prompt_template: str) -> None`** in `src/merge.py`:

1. Read front text file (may be empty)
2. Read back text file (may be empty)
3. Load the prompt template and substitute `{front_text}` and `{back_text}` placeholders
4. Send to Ollama (`gemma4:e2b` model) via the `ollama` Python client
5. Parse the JSON from the LLM response (strip markdown fences if present)
6. Add the `source` field (front/back text file names)
7. Validate that the response has the expected top-level keys
8. Write to `output_path` as formatted JSON

## Prompt Design

The prompt is stored in `prompts/extract_person.txt` — a plain text file the user can edit.

The prompt includes:
- Role instruction (genealogy data extraction assistant)
- Rules for handling both front and back text
- Date format requirements (ISO 8601)
- Deduction rules (e.g., birth date from death date minus age)
- Confidence scoring guidelines
- Known place names from the Arrondissement Aalst area
- Common OCR misspelling corrections
- The JSON schema to follow
- Placeholders for `{front_text}` and `{back_text}`

### Known Places (Arrondissement Aalst, Oost-Vlaanderen)

The prompt includes these place names so the LLM can normalize OCR misspellings:

**Haaltert municipality:** Haaltert, Denderhoutem, Heldergem, Kerksken, Terjoden

**Aalst municipality:** Aalst, Baardegem, Erembodegem, Gijzegem, Herdersem, Hofstade, Meldert, Moorsel, Nieuwerkerken

**Nearby municipalities:** Denderleeuw, Iddergem, Erpe-Mere, Aaigem, Bambrugge, Burst, Erondegem, Erpe, Mere, Ottergem, Vlekkem, Herzele, Borsbeke, Hillegem, Ressegem, Sint-Antelinks, Sint-Lievens-Esse, Lede, Impe, Oordegem, Smetlede, Wanzele, Ninove, Zottegem, Geraardsbergen, Dendermonde, Welle, Lemberge, Tiedekerk

### Common OCR Misspellings

Haeltert → Haaltert, Kerkxken → Kerksken, Haciltert → Haaltert, Denderhautem → Denderhoutem, Tiedekérke → Tiedekerk, Aygem → Aaigem

## Pipeline Integration

The LLM step is added to the existing `main()` flow, after OCR:

1. Find pairs in `input/` (existing)
2. Create `output/`, `output/text/`, `output/json/` directories
3. For each matched pair:
   - Stitch front + back into `output/{front_filename}` (existing)
   - Extract text from front scan → `output/text/{front_stem}_front.txt` (existing)
   - Extract text from back scan → `output/text/{back_stem}_back.txt` (existing)
   - Interpret text → `output/json/{front_stem}.json` (new)
4. If interpretation fails on a card, log it as an error but continue processing
5. Print summary at the end

## Output Structure

```
output/
├── Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg
├── text/
│   ├── Meganck Dominicus Kerksken bidprentje 21 december 1913_front.txt
│   └── Meganck Dominicus Kerksken bidprentje 21 december 1913 1_back.txt
├── json/
│   └── Meganck Dominicus Kerksken bidprentje 21 december 1913.json
prompts/
  └── extract_person.txt
```

## Error Handling

- If Ollama is not installed: `run.sh` prints install instructions and exits
- If model is not pulled: `run.sh` auto-pulls `gemma4:e2b`
- If Ollama service is not running: Python code detects connection error on the first card, logs a single warning, skips ALL remaining interpretations (no point retrying 20 more times)
- If LLM returns invalid JSON: log error, skip this card, continue
- If LLM times out: log error, skip this card, continue
- Interpretation errors are collected and printed in the end-of-run summary

## Console Output

```
Found 21 pairs in input/
[ 1/21] Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg  OK
[ 2/21] Van den Bruele Frans Haaltert  bidprentje 05 januari 1898.jpeg  OK
...

Done: 21 merged, 21 text extracted, 21 interpreted, 0 errors
```

## run.sh Updates

Add Ollama check and model auto-pull after the Tesseract checks:

```bash
# Check Ollama is available
if ! command -v ollama &>/dev/null; then
    echo "Error: ollama is required but not found."
    echo "Install it with: brew install ollama"
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

## Testing

- **Unit test for `interpret_text`:** Mock the Ollama client to return a known JSON response. Verify the output file is created with correct structure.
- **Unit test for JSON parsing:** Test that the function handles malformed LLM responses gracefully (invalid JSON, missing fields).
- **Unit test for prompt loading:** Verify that `{front_text}` and `{back_text}` placeholders are correctly substituted.
- **Integration:** Run on actual memorial card text files to verify extraction quality.
