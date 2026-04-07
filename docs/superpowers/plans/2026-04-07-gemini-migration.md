# Gemini API Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Ollama with the Google Gemini API for faster LLM extraction (sub-second vs 3-10s per card).

**Architecture:** Swap the `ollama` Python SDK for the `google-genai` SDK in `extract.py`. API key stored in a local `config.json` (gitignored). Both `interpret_text` (structured JSON extraction) and `verify_dates` (vision-based year reading) are migrated. Callers (`main.py`, `server.py`) updated to load config instead of checking Ollama.

**Tech Stack:** Python, `google-genai` SDK, Gemini 2.0 Flash, Tesseract OCR

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `config.json` | Create | API key storage (gitignored, not committed) |
| `.gitignore` | Modify | Add `config.json` |
| `requirements.txt` | Modify | Swap `ollama` for `google-genai` |
| `src/extract.py` | Modify | Replace Ollama calls with Gemini SDK |
| `src/main.py` | Modify | Load config, remove Ollama checks |
| `src/server.py` | Modify | Load config, remove Ollama checks |
| `run.sh` | Modify | Remove Ollama checks, add config check |

---

### Task 1: Config file, .gitignore, and requirements

**Files:**
- Create: `config.json`
- Modify: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: Create `config.json`**

Create `config.json` at the project root:

```json
{
  "gemini_api_key": "AIzaSyCRCqfcYe0FbIZjHOljgZVp3M3CPx-bHvs"
}
```

- [ ] **Step 2: Add `config.json` to `.gitignore`**

Add `config.json` to the end of `.gitignore`. The file currently contains:

```
input/
output/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
.superpowers/
```

Add `config.json` as the last line.

- [ ] **Step 3: Update `requirements.txt`**

Replace the contents of `requirements.txt` with:

```
Pillow>=10.0
pytest>=8.0
pytesseract>=0.3.10
google-genai>=1.0
```

(Removed `ollama>=0.4`, added `google-genai>=1.0`)

- [ ] **Step 4: Install the new dependency**

```bash
.venv/bin/pip install -r requirements.txt
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt
git commit -m "chore: add config.json to gitignore, swap ollama for google-genai

config.json stores the Gemini API key locally (not committed).
requirements.txt now uses google-genai instead of ollama."
```

**Do NOT commit `config.json` — it contains the API key.**

---

### Task 2: Replace Ollama with Gemini in `src/extract.py`

**Files:**
- Modify: `src/extract.py`

This is the core change. Replace all Ollama SDK usage with Google GenAI SDK.

- [ ] **Step 1: Update imports and module-level setup**

Replace lines 1-12 of `src/extract.py`:

```python
# src/extract.py
import json
import os
import re
from pathlib import Path
from PIL import Image
import ollama
import pytesseract

_YEAR_RE = re.compile(r"^\d{4}$")

MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
```

With:

```python
# src/extract.py
import json
import re
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types
import pytesseract

_YEAR_RE = re.compile(r"^\d{4}$")

GEMINI_MODEL = "gemini-2.0-flash"
```

- [ ] **Step 2: Update `PERSON_SCHEMA` for Gemini compatibility**

Gemini's `response_json_schema` does not support `{"type": ["string", "null"]}` union syntax. Instead, use `"nullable": true` with a single type. Replace the `PERSON_SCHEMA` (lines 14-41) with:

```python
PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "nullable": True},
                "last_name": {"type": "string", "nullable": True},
                "birth_date": {"type": "string", "nullable": True},
                "birth_place": {"type": "string", "nullable": True},
                "death_date": {"type": "string", "nullable": True},
                "death_place": {"type": "string", "nullable": True},
                "age_at_death": {"type": "integer", "nullable": True},
                "spouses": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouses",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}
```

- [ ] **Step 3: Add a helper to create the Gemini client**

Add this function after `PERSON_SCHEMA` and before `_clean_ocr_text`:

```python
def _make_gemini_client(config_path: Path) -> genai.Client:
    """Create a Gemini client from the config file."""
    config = json.loads(config_path.read_text())
    return genai.Client(api_key=config["gemini_api_key"])
```

- [ ] **Step 4: Update `verify_dates` to use Gemini**

Replace the `verify_dates` function. The key changes:
- Accepts a `client: genai.Client` parameter
- Uses `client.models.generate_content` with a PIL image instead of `ollama.chat` with an image path
- No more `keep_alive`, no more `MODEL` constant

Replace the entire `verify_dates` function (lines 73-151) with:

```python
def verify_dates(image_path: Path, text_path: Path, client: genai.Client, conflicts_dir: Path | None = None) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking Gemini.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to Gemini for visual verification.
    If Gemini reads a different year, the text file is updated in place and
    the crop image is saved to conflicts_dir for manual review.

    Returns a list of corrections made (empty if all years match).
    """
    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, lang="nld", output_type=pytesseract.Output.DICT)

    # Collect year words and their bounding boxes
    years: list[dict] = []
    for i, word in enumerate(data["text"]):
        clean_word = word.strip().rstrip(",.")
        if _YEAR_RE.match(clean_word):
            years.append({
                "ocr_year": clean_word,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            })

    if not years:
        return []

    corrections = []
    text = text_path.read_text()

    for entry in years:
        pad = 10
        crop = image.crop((
            max(0, entry["left"] - pad),
            max(0, entry["top"] - pad),
            entry["left"] + entry["width"] + pad,
            entry["top"] + entry["height"] + pad,
        ))

        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
                crop,
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=16,
            ),
        )
        llm_year = resp.text.strip().rstrip(",.")

        if (
            _YEAR_RE.match(llm_year)
            and llm_year != entry["ocr_year"]
            and 1800 <= int(llm_year) <= 1950
        ):
            text = text.replace(entry["ocr_year"], llm_year, 1)
            corrections.append(f"{entry['ocr_year']} -> {llm_year}")

            # Save the crop for manual review
            if conflicts_dir:
                conflicts_dir.mkdir(exist_ok=True)
                stem = image_path.stem
                conflict_path = conflicts_dir / f"{stem}_ocr{entry['ocr_year']}_llm{llm_year}.png"
                crop.save(conflict_path)

    if corrections:
        text_path.write_text(text)

    return corrections
```

Key differences from the Ollama version:
- `client: genai.Client` parameter added
- PIL `crop` image passed directly in `contents` list (Gemini accepts PIL images natively)
- No temporary file saving/cleanup needed for image
- Uses `resp.text` instead of `resp.message.content`

- [ ] **Step 5: Update `interpret_text` to use Gemini**

Replace the entire `interpret_text` function with:

```python
def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
    client: genai.Client,
) -> None:
    """Interpret OCR text using Gemini and write structured JSON.

    Sends the static system prompt and card-specific user message to Gemini
    with structured JSON output. Writes the parsed JSON to output_path.
    Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    user_message = user_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_json_schema=PERSON_SCHEMA,
        ),
    )

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response.text[:200]}"
        ) from e

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 6: Update `_extract_one`**

Replace the `_extract_one` function. Changes:
- `ollama_available: bool` becomes `client: genai.Client | None`
- `verify_dates` and `interpret_text` calls pass `client`

```python
def _extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    client: genai.Client | None,
    system_prompt: str | None,
    user_template: str | None,
    on_step=None,
) -> dict:
    """Process extraction for a single pair: OCR, date verification, LLM interpretation.

    on_step: optional callback(step_name) called before each pipeline stage.
    """
    result = {
        "front_name": front_path.name,
        "ocr": False,
        "verify_corrections": 0,
        "interpreted": False,
        "errors": [],
        "date_fixes": [],
    }

    front_text_path = text_dir / f"{front_path.stem}_front.txt"
    back_text_path = text_dir / f"{back_path.stem}_back.txt"

    # OCR Front
    if on_step:
        on_step("ocr_front")
    try:
        extract_text(front_path, front_text_path)
    except Exception as e:
        result["errors"].append(f"{front_path.name} OCR front: {e}")
        return result

    # OCR Back
    if on_step:
        on_step("ocr_back")
    try:
        extract_text(back_path, back_text_path)
        result["ocr"] = True
    except Exception as e:
        result["errors"].append(f"{front_path.name} OCR back: {e}")
        return result

    # Date verification (LLM visual cross-check)
    if client:
        if on_step:
            on_step("date_verify")
        try:
            for txt_path, img_path in [(front_text_path, front_path), (back_text_path, back_path)]:
                corrections = verify_dates(img_path, txt_path, client, conflicts_dir)
                for c in corrections:
                    result["verify_corrections"] += 1
                    result["date_fixes"].append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result["errors"].append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if client:
        if on_step:
            on_step("llm_extract")
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(front_text_path, back_text_path, json_output_path, system_prompt, user_template, client)
            result["interpreted"] = True
        except Exception as e:
            result["errors"].append(f"{front_path.name} interpret: {e}")

    return result
```

- [ ] **Step 7: Update `extract_all`**

Replace `extract_all`. Changes: `ollama_available: bool` becomes `client: genai.Client | None`.

```python
def extract_all(
    pairs: list[tuple[Path, Path]],
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    system_prompt: str | None,
    user_template: str | None,
    client: genai.Client | None,
    force: bool = False,
) -> tuple[int, int, int, int, int, list[str]]:
    """Run extraction on all pairs. Returns (text_count, verify_count, interpret_count, skipped, processed, errors)."""
    to_process = []
    skipped = 0

    for front_path, back_path in pairs:
        json_output_path = json_dir / f"{front_path.stem}.json"
        if not force and json_output_path.exists():
            skipped += 1
        else:
            to_process.append((front_path, back_path))

    text_count = 0
    verify_count = 0
    interpret_count = 0
    all_errors: list[str] = []
    total = len(to_process)
    width = len(str(total)) if total else 1

    if skipped:
        print(f"Skipping {skipped} already extracted")

    for idx, (front_path, back_path) in enumerate(to_process, 1):
        result = _extract_one(
            front_path, back_path,
            text_dir, json_dir, conflicts_dir,
            client, system_prompt, user_template,
        )

        for fix in result["date_fixes"]:
            print(f"        {fix}")

        pair_ok = not result["errors"]
        name = result["front_name"]
        if pair_ok:
            print(f"  [{idx:>{width}}/{total}] {name}  OK")
        else:
            print(f"  [{idx:>{width}}/{total}] {name}  ERROR")

        text_count += result["ocr"]
        verify_count += result["verify_corrections"]
        interpret_count += result["interpreted"]
        all_errors.extend(result["errors"])

    return text_count, verify_count, interpret_count, skipped, total, all_errors
```

- [ ] **Step 8: Verify syntax**

```bash
python -c "import ast; ast.parse(open('src/extract.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add src/extract.py
git commit -m "feat: replace Ollama with Gemini API in extraction pipeline

Uses google-genai SDK with gemini-2.0-flash model. Both interpret_text
(structured JSON extraction) and verify_dates (vision-based year reading)
now use Gemini. Accepts a genai.Client instead of ollama_available bool."
```

---

### Task 3: Update `src/main.py`

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Replace the entire `src/main.py`**

```python
# src/main.py
import argparse
from pathlib import Path
import webbrowser

from src.merge import find_pairs, merge_all
from src.extract import extract_all, _make_gemini_client
from src.server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Memorial card processing pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["merge", "extract", "all", "serve"],
        help="Which phase to run (default: serve)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all pairs, even if output already exists",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    text_dir = output_dir / "text"
    json_dir = output_dir / "json"
    conflicts_dir = output_dir / "date_conflicts"
    prompts_dir = script_dir / "prompts"
    config_path = script_dir / "config.json"

    # --- Serve (web UI) ---
    if args.command == "serve":
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        json_dir.mkdir(exist_ok=True)

        server = make_server(json_dir, input_dir, output_dir)
        port = server.server_address[1]
        url = f"http://localhost:{port}"
        print(f"Memorial Card Digitizer running at {url}")
        print("Press Ctrl+C to stop.")
        webbrowser.open(url)
        server.serve_forever()
        return

    if not input_dir.exists():
        input_dir.mkdir()
        print(f"Created {input_dir}/ — drop your scans there and run again.")
        return

    pairs, pairing_errors = find_pairs(input_dir)

    if not pairs and not pairing_errors:
        print("No scans found in input/. Drop front + back JPEG pairs there and run again.")
        return

    output_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)
    json_dir.mkdir(exist_ok=True)

    total = len(pairs)
    print(f"Found {total} pair{'s' if total != 1 else ''} in input/")

    all_errors: list[str] = list(pairing_errors)
    ok_count = 0
    merge_skipped = 0
    text_count = 0
    verify_count = 0
    interpret_count = 0
    extract_skipped = 0

    # --- Merge phase ---
    if args.command in ("merge", "all"):
        print("\n--- Merge ---")
        ok_count, merge_skipped, merge_errors = merge_all(pairs, output_dir, force=args.force)
        all_errors.extend(merge_errors)

    # --- Extract phase ---
    if args.command in ("extract", "all"):
        # Load prompt files
        system_prompt_path = prompts_dir / "extract_person_system.txt"
        user_template_path = prompts_dir / "extract_person_user.txt"
        system_prompt = None
        user_template = None
        if system_prompt_path.exists() and user_template_path.exists():
            system_prompt = system_prompt_path.read_text()
            user_template = user_template_path.read_text()
        else:
            print(f"Warning: prompt files not found in {prompts_dir} — skipping interpretation")

        # Create Gemini client
        client = None
        if system_prompt:
            if config_path.exists():
                try:
                    client = _make_gemini_client(config_path)
                except Exception as e:
                    print(f"Warning: Failed to create Gemini client ({e}) — skipping LLM steps")
            else:
                print(f"Warning: {config_path} not found — skipping LLM steps")

        print("\n--- Extract ---")
        text_count, verify_count, interpret_count, extract_skipped, _, extract_errors = extract_all(
            pairs, text_dir, json_dir, conflicts_dir,
            system_prompt, user_template, client, force=args.force,
        )
        all_errors.extend(extract_errors)

    # --- Summary ---
    parts = []
    if args.command in ("merge", "all"):
        skip_note = f" ({merge_skipped} skipped)" if merge_skipped else ""
        parts.append(f"{ok_count} merged{skip_note}")
    if args.command in ("extract", "all"):
        skip_note = f" ({extract_skipped} skipped)" if extract_skipped else ""
        parts.append(f"{text_count} text extracted{skip_note}")
        parts.append(f"{verify_count} date{'s' if verify_count != 1 else ''} corrected")
        parts.append(f"{interpret_count} interpreted")
    parts.append(f"{len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    print(f"\nDone: {', '.join(parts)}")

    if all_errors:
        print(f"\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "refactor: use Gemini client instead of Ollama in main.py

Loads config.json for Gemini API key. Removes ollama import and
reachability check. Passes genai.Client to extract_all."
```

---

### Task 4: Update `src/server.py`

**Files:**
- Modify: `src/server.py`

Three areas need updating:

- [ ] **Step 1: Update `ExtractionWorker.start` and `_run` signatures**

Replace `ollama_available` with `client` in both methods.

In `ExtractionWorker.start` (around line 714-715), replace:

```python
    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              system_prompt, user_template, ollama_available, force):
```

With:

```python
    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              system_prompt, user_template, client, force):
```

- [ ] **Step 2: Update thread args in `start`**

Replace (around line 731-732):

```python
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, ollama_available, force),
```

With:

```python
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, client, force),
```

- [ ] **Step 3: Update `_run` signature**

Replace (around line 744-745):

```python
    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             system_prompt, user_template, ollama_available, force):
```

With:

```python
    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             system_prompt, user_template, client, force):
```

- [ ] **Step 4: Update `_extract_one` call in `_run`**

Replace (around line 772-776):

```python
            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, system_prompt, user_template,
                on_step=_on_step,
            )
```

With:

```python
            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                client, system_prompt, user_template,
                on_step=_on_step,
            )
```

- [ ] **Step 5: Update the POST `/api/extract` handler**

Replace the Ollama loading/checking block (around lines 950-976):

```python
            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            user_template_path = prompts_dir / "extract_person_user.txt"
            system_prompt = None
            user_template = None
            if system_prompt_path.exists() and user_template_path.exists():
                system_prompt = system_prompt_path.read_text()
                user_template = user_template_path.read_text()

            # Check Ollama availability
            ollama_available = False
            if system_prompt:
                try:
                    import ollama as ollama_client
                    ollama_client.list()
                    ollama_available = True
                except Exception:
                    pass

            if not ollama_available and system_prompt:
                self._send_json({"status": "error", "error": "Ollama is not running. Start it with `ollama serve`."}, 503)
                return

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, ollama_available, force,
            )
```

With:

```python
            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            user_template_path = prompts_dir / "extract_person_user.txt"
            system_prompt = None
            user_template = None
            if system_prompt_path.exists() and user_template_path.exists():
                system_prompt = system_prompt_path.read_text()
                user_template = user_template_path.read_text()

            # Create Gemini client
            from src.extract import _make_gemini_client
            config_path = input_dir.parent / "config.json"
            client = None
            if system_prompt:
                if config_path.exists():
                    try:
                        client = _make_gemini_client(config_path)
                    except Exception as e:
                        self._send_json({"status": "error", "error": f"Failed to create Gemini client: {e}"}, 503)
                        return
                else:
                    self._send_json({"status": "error", "error": "config.json not found. Create it with your Gemini API key."}, 503)
                    return

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, client, force,
            )
```

- [ ] **Step 6: Commit**

```bash
git add src/server.py
git commit -m "refactor: use Gemini client instead of Ollama in server.py

ExtractionWorker and POST /api/extract now create a Gemini client
from config.json instead of checking Ollama availability."
```

---

### Task 5: Update `run.sh`

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh` contents**

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

# Check config.json exists
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo "Error: config.json not found."
    echo "Create it with your Gemini API key:"
    echo '  {"gemini_api_key": "your-api-key-here"}'
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    echo "Setup complete."
    echo ""
fi

# Run the pipeline
"$VENV_DIR/bin/python" "$SCRIPT_DIR/src/main.py" "$@"
```

- [ ] **Step 2: Commit**

```bash
git add run.sh
git commit -m "refactor: replace Ollama checks with config.json check in run.sh

run.sh no longer checks for Ollama or pulls models. Instead it
verifies config.json exists with the Gemini API key."
```
