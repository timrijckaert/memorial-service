# Ollama KV Cache Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up LLM extraction by enabling Ollama's KV cache reuse on the static system prompt across sequential card processing.

**Architecture:** Split the combined prompt into system (static instructions) and user (card text) messages so Ollama caches the system prefix. Process cards sequentially to maintain cache hits. Add `keep_alive` to prevent model unloading between cards.

**Tech Stack:** Python, Ollama Python SDK, Tesseract OCR

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `prompts/extract_person_system.txt` | Create | Static system instructions (genealogy rules, places, OCR corrections) |
| `prompts/extract_person_user.txt` | Create | Card text template with `{front_text}` and `{back_text}` placeholders |
| `prompts/extract_person.txt` | Delete | Replaced by the two files above |
| `src/extract.py` | Modify | Split messages, keep_alive, sequential processing |
| `src/main.py` | Modify | Load two prompt files, pass both to extract pipeline |
| `src/server.py` | Modify | Load two prompt files, pass both through ExtractionWorker |

---

### Task 1: Split the prompt file

**Files:**
- Create: `prompts/extract_person_system.txt`
- Create: `prompts/extract_person_user.txt`
- Delete: `prompts/extract_person.txt`

- [ ] **Step 1: Create the system prompt file**

Create `prompts/extract_person_system.txt` with lines 1-109 of the current `extract_person.txt` (everything before `--- FRONT TEXT ---`):

```text
You are a genealogy data extraction assistant.
Extract biographical information from Belgian memorial cards (bidprentjes).
The text was extracted via OCR and may contain errors.

ABOUT BIDPRENTJES (memorial cards):
Belgian memorial cards typically follow this structure:
- FRONT: Often contains a prayer, with the deceased's name at the top. Below the name there may be birth/death details.
- BACK: A prayer text, sometimes repeating the deceased's name and dates. The back often contains the most complete biographical information (birth place, death place, spouse, parents, age).
- The deceased's name is most reliably found at the beginning of the biographical text or repeated on the back of the card.
- IGNORE printer marks at the bottom of the card (drukker), e.g. "Drukk. A. Redant en zoon", "Drukkerij Dacquin", "Imp. Vande Velde" — not biographical information.
- IGNORE all religious text: prayers, "Bid voor de ziel van", indulgence references (e.g. "100 d. afl."), saint invocations, Bible verses, and any other devotional content. Only extract biographical facts.

IMPORTANT RULES:
- Both front and back text are provided. Check BOTH for information — names can appear on either side.
- Return dates in ISO 8601 format (YYYY-MM-DD).
- All dates must fall in the range 1800–1950. Any year outside this range is likely an OCR error.
- OCR often misreads digits (e.g. 4 vs 1, 8 vs 3, 0 vs 6). Cross-check dates against context: if the text says someone died at a certain age, verify the dates are arithmetically consistent.
- Age at death must be plausible (typically under 110). If the computed age exceeds 110, suspect an OCR error in one of the dates and add a note.
- If a birth date is not explicitly stated but death date and age at death are given, deduce the approximate birth date and note this in the notes array.
- "aldaar" (meaning "at that place") refers back to the most recently mentioned location. For example, if someone was born in Denderhoutem and the text says "aldaar overleden", the death place is also Denderhoutem.
- Normalize place names to their modern Dutch spelling using the known places list below.
- Add a note whenever you deduce a value, correct an OCR error, or are uncertain about an extraction.
- For spouses: extract the full name of every spouse as a list of strings, in marriage order (1st marriage first). Set to an empty list [] if no spouse is mentioned. When the text mentions multiple marriages (e.g. "weduwe in 't 1e huwelijk van X, in 't 2e huwelijk van Y"), include ALL spouse names — do not relegate later marriages to notes.
- CRITICAL — distinguishing parents from spouses on Dutch memorial cards:
  - "zoon van" / "dochter van" / "kind van" = "son of" / "daughter of" / "child of" → these introduce PARENTS. Ignore these names — do NOT extract them.
  - "echtgenoot van" / "echtgenote van" / "man van" / "vrouw van" = "husband of" / "wife of" → these introduce a SPOUSE.
  - "weduwnaar van" / "weduwe van" = "widower of" / "widow of" → these introduce a DECEASED SPOUSE.
  - Do NOT confuse a parent's name for a spouse. Pay close attention to the keyword preceding the name.
- For age_at_death: ONLY populate this field when either birth_date or death_date is missing and you are using the age to deduce the missing date. If both birth_date and death_date are explicitly stated, set age_at_death to null — it is redundant.

OUTPUT FIELDS:
- first_name: Given/first name(s) of the deceased
- last_name: Family/surname of the deceased
- birth_date: Date of birth in YYYY-MM-DD format
- birth_place: Place of birth (normalized to modern spelling)
- death_date: Date of death in YYYY-MM-DD format
- death_place: Place of death (normalized to modern spelling)
- age_at_death: Age at death as an integer (ONLY when needed to deduce a missing date, otherwise null)
- spouses: List of full spouse names in marriage order (1st marriage first). Empty list if none.
- notes: Array of strings explaining deductions, corrections, uncertainties

KNOWN PLACES (Arrondissement Aalst, Oost-Vlaanderen, Belgium):
- Haaltert
- Denderhoutem
- Heldergem
- Kerksken
- Terjoden
- Aalst
- Baardegem
- Erembodegem
- Gijzegem
- Herdersem
- Hofstade
- Meldert
- Moorsel
- Nieuwerkerken
- Denderleeuw
- Iddergem
- Erpe-Mere
- Aaigem
- Bambrugge
- Burst
- Erondegem
- Erpe
- Mere
- Ottergem
- Vlekkem
- Herzele
- Borsbeke
- Hillegem
- Ressegem
- Sint-Antelinks
- Sint-Lievens-Esse
- Lede
- Impe
- Oordegem
- Smetlede
- Wanzele
- Ninove
- Zottegem
- Geraardsbergen
- Dendermonde
- Welle
- Lemberge
- Liedekerke

ARCHAIC / REGIONAL DUTCH MONTH NAMES:
Some memorial cards use old Dutch or regional month names. Treat these as their modern equivalents:
- Louwmaand / Loumaand -> Januari (January)
- Sprokkelmaand -> Februari (February)
- Lentemaand -> Maart (March)
- Grasmaand -> April
- Bloeimaand -> Mei (May)
- Zomermaand / Weidemaand -> Juni (June)
- Hooimaand -> Juli (July)
- Oogst / Oogstmaand -> Augustus (August)
- Herfstmaand / Gerstmaand -> September
- Wijnmaand -> Oktober (October)
- Slachtmaand -> November
- Wintermaand -> December

COMMON OCR MISSPELLINGS:
Haeltert -> Haaltert,
Kerkxken -> Kerksken,
Haciltert -> Haaltert,
Denderhautem -> Denderhoutem,
Tiedekérke -> Liedekerke,
Aygem -> Aaigem
Tiedekerk -> Liedekerke
```

- [ ] **Step 2: Create the user prompt template file**

Create `prompts/extract_person_user.txt`:

```text
--- FRONT TEXT ---
{front_text}

--- BACK TEXT ---
{back_text}
```

- [ ] **Step 3: Delete the old combined prompt file**

```bash
git rm prompts/extract_person.txt
```

- [ ] **Step 4: Commit**

```bash
git add prompts/extract_person_system.txt prompts/extract_person_user.txt
git commit -m "refactor: split prompt into system and user template files

Splits extract_person.txt into extract_person_system.txt (static
instructions) and extract_person_user.txt (card text template).
This enables Ollama KV cache reuse on the system prompt prefix."
```

---

### Task 2: Update `interpret_text` to use split messages and `keep_alive`

**Files:**
- Modify: `src/extract.py:1-9` (imports)
- Modify: `src/extract.py:154-192` (`interpret_text` function)

- [ ] **Step 1: Remove the `concurrent.futures` import**

In `src/extract.py`, remove the `concurrent.futures` import on line 2 (no longer needed after Task 3 removes the ThreadPoolExecutor):

Replace line 2:
```python
import concurrent.futures
```
With nothing (delete the line).

- [ ] **Step 2: Update `interpret_text` signature and implementation**

Replace the entire `interpret_text` function (lines 154-192) with:

```python
def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    system_prompt: str,
    user_template: str,
) -> None:
    """Interpret OCR text using a local LLM and write structured JSON.

    Sends the static system prompt and card-specific user message as separate
    messages to Ollama, enabling KV cache reuse on the system prefix.
    Writes the parsed JSON to output_path. Raises on failure (caller handles).
    """
    front_text = front_text_path.read_text() if front_text_path.exists() else ""
    back_text = back_text_path.read_text() if back_text_path.exists() else ""

    user_message = user_template.replace("{front_text}", front_text).replace(
        "{back_text}", back_text
    )

    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        format=PERSON_SCHEMA,
        options={"temperature": 0, "num_predict": 2048},
        keep_alive="30m",
    )

    try:
        result = json.loads(response.message.content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response.message.content[:200]}"
        ) from e

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 3: Add `keep_alive` to `verify_dates`**

In the `verify_dates` function, add `keep_alive="30m"` to the `ollama.chat` call (around line 120-128). Replace:

```python
            resp = ollama.chat(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
                    "images": [str(crop_path)],
                }],
                options={"temperature": 0, "num_predict": 16},
            )
```

With:

```python
            resp = ollama.chat(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
                    "images": [str(crop_path)],
                }],
                options={"temperature": 0, "num_predict": 16},
                keep_alive="30m",
            )
```

- [ ] **Step 4: Commit**

```bash
git add src/extract.py
git commit -m "refactor: split LLM messages and add keep_alive in extract.py

interpret_text now accepts separate system_prompt and user_template
strings, sending them as system/user messages to enable Ollama KV
cache reuse. Added keep_alive=30m to both interpret and verify calls."
```

---

### Task 3: Update `_extract_one` and `extract_all` for new signature and sequential processing

**Files:**
- Modify: `src/extract.py:195-328` (`_extract_one` and `extract_all`)

- [ ] **Step 1: Update `_extract_one` signature and `interpret_text` call**

Replace the `_extract_one` function (lines 195-264) with:

```python
def _extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    ollama_available: bool,
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
    if ollama_available:
        if on_step:
            on_step("date_verify")
        try:
            for txt_path, img_path in [(front_text_path, front_path), (back_text_path, back_path)]:
                corrections = verify_dates(img_path, txt_path, conflicts_dir)
                for c in corrections:
                    result["verify_corrections"] += 1
                    result["date_fixes"].append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result["errors"].append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if ollama_available:
        if on_step:
            on_step("llm_extract")
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(front_text_path, back_text_path, json_output_path, system_prompt, user_template)
            result["interpreted"] = True
        except Exception as e:
            result["errors"].append(f"{front_path.name} interpret: {e}")

    return result
```

- [ ] **Step 2: Update `extract_all` to use sequential processing and new signature**

Replace the `extract_all` function (lines 267-328) with:

```python
def extract_all(
    pairs: list[tuple[Path, Path]],
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    system_prompt: str | None,
    user_template: str | None,
    ollama_available: bool,
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
            ollama_available, system_prompt, user_template,
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

- [ ] **Step 3: Commit**

```bash
git add src/extract.py
git commit -m "refactor: sequential processing and split prompt params in extract pipeline

_extract_one and extract_all now accept system_prompt and user_template
instead of prompt_template. extract_all uses a simple for loop instead
of ThreadPoolExecutor(max_workers=4) for sequential processing, enabling
Ollama KV cache reuse across cards."
```

---

### Task 4: Update `src/main.py` to load two prompt files

**Files:**
- Modify: `src/main.py:35` (prompt_path)
- Modify: `src/main.py:84-106` (extract phase)

- [ ] **Step 1: Update prompt loading and extract_all call**

In `src/main.py`, replace line 35:

```python
    prompt_path = script_dir / "prompts" / "extract_person.txt"
```

With:

```python
    prompts_dir = script_dir / "prompts"
```

Then replace the extract phase (lines 85-106) with:

```python
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

        # Pre-flight check: is Ollama reachable?
        ollama_available = False
        if system_prompt:
            try:
                ollama.list()
                ollama_available = True
            except Exception as e:
                print(f"Warning: Ollama not reachable ({e}) — skipping LLM steps")

        print("\n--- Extract ---")
        text_count, verify_count, interpret_count, extract_skipped, _, extract_errors = extract_all(
            pairs, text_dir, json_dir, conflicts_dir,
            system_prompt, user_template, ollama_available, force=args.force,
        )
        all_errors.extend(extract_errors)
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "refactor: load split prompt files in main.py

main.py now loads extract_person_system.txt and extract_person_user.txt
separately and passes both to extract_all."
```

---

### Task 5: Update `src/server.py` to load two prompt files and pass through

**Files:**
- Modify: `src/server.py:714-715` (ExtractionWorker.start signature)
- Modify: `src/server.py:731-732` (ExtractionWorker.start thread args)
- Modify: `src/server.py:744-745` (ExtractionWorker._run signature)
- Modify: `src/server.py:772-775` (ExtractionWorker._run _extract_one call)
- Modify: `src/server.py:950-972` (POST /api/extract handler)

- [ ] **Step 1: Update `ExtractionWorker.start` signature**

Replace lines 714-715:

```python
    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              prompt_template, ollama_available, force):
```

With:

```python
    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              system_prompt, user_template, ollama_available, force):
```

- [ ] **Step 2: Update the thread args in `start`**

Replace lines 731-732:

```python
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  prompt_template, ollama_available, force),
```

With:

```python
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, ollama_available, force),
```

- [ ] **Step 3: Update `_run` signature**

Replace lines 744-745:

```python
    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             prompt_template, ollama_available, force):
```

With:

```python
    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             system_prompt, user_template, ollama_available, force):
```

- [ ] **Step 4: Update `_extract_one` call in `_run`**

Replace lines 772-776:

```python
            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, prompt_template,
                on_step=_on_step,
            )
```

With:

```python
            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, system_prompt, user_template,
                on_step=_on_step,
            )
```

- [ ] **Step 5: Update the POST /api/extract handler**

Replace lines 950-972:

```python
            # Load prompt template
            prompt_path = input_dir.parent / "prompts" / "extract_person.txt"
            prompt_template = None
            if prompt_path.exists():
                prompt_template = prompt_path.read_text()

            # Check Ollama availability
            ollama_available = False
            if prompt_template:
                try:
                    import ollama as ollama_client
                    ollama_client.list()
                    ollama_available = True
                except Exception:
                    pass

            if not ollama_available and prompt_template:
                self._send_json({"status": "error", "error": "Ollama is not running. Start it with `ollama serve`."}, 503)
                return

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                prompt_template, ollama_available, force,
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

- [ ] **Step 6: Commit**

```bash
git add src/server.py
git commit -m "refactor: load split prompt files in server.py

ExtractionWorker and the POST /api/extract handler now load
extract_person_system.txt and extract_person_user.txt separately,
passing both through the extraction pipeline."
```
