# src/extract.py
import concurrent.futures
import json
import os
import re
from pathlib import Path
from PIL import Image
import ollama
import pytesseract

_YEAR_RE = re.compile(r"^\d{4}$")

MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")

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
                "spouses": {"type": "array", "items": {"type": "string"}},
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
                "death_date", "death_place", "age_at_death", "spouses", "parents",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}


def _clean_ocr_text(raw: str) -> str:
    """Clean raw OCR output: rejoin hyphenated words, remove noise lines, collapse whitespace."""
    # Rejoin words split across lines with a hyphen
    text = re.sub(r"-\n\s*", "", raw)
    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)

    cleaned_lines = []
    for line in text.split("\n"):
        line = line.strip()
        # Drop lines without a real word (3+ letters) — filters decorative noise
        if line and not re.search(r"[a-zA-ZÀ-ÿ]{3,}", line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Cleans OCR artifacts (noise lines,
    broken hyphenation, excessive whitespace). Creates the output file even
    if no text is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    raw = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(_clean_ocr_text(raw))


def verify_dates(image_path: Path, text_path: Path, conflicts_dir: Path | None = None) -> list[str]:
    """Verify year digits in OCR text by cropping them from the image and asking the LLM.

    Uses Tesseract's bounding-box data to locate year-like words (4 digits),
    crops each region, and sends the crop to the LLM for visual verification.
    If the LLM reads a different year, the text file is updated in place and
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

        # Save crop to a temporary file for the LLM (include stem for thread safety)
        crop_path = text_path.parent / f"_crop_{text_path.stem}_{entry['ocr_year']}.png"
        crop.save(crop_path)

        try:
            resp = ollama.chat(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
                    "images": [str(crop_path)],
                }],
                options={"temperature": 0, "num_predict": 16},
            )
            llm_year = resp.message.content.strip().rstrip(",.")

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
        finally:
            crop_path.unlink(missing_ok=True)

    if corrections:
        text_path.write_text(text)

    return corrections


def interpret_text(
    front_text_path: Path,
    back_text_path: Path,
    output_path: Path,
    prompt_template: str,
) -> None:
    """Interpret OCR text using a local LLM and write structured JSON.

    Reads front and back text files, substitutes them into the prompt template,
    sends to Ollama with a structured output schema, and writes the parsed JSON
    to output_path. Raises on failure (caller handles).
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
        options={"temperature": 0, "num_predict": 2048},
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


def _extract_one(
    front_path: Path,
    back_path: Path,
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    ollama_available: bool,
    prompt_template: str | None,
) -> dict:
    """Process extraction for a single pair: OCR, date verification, LLM interpretation."""
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

    # OCR
    try:
        extract_text(front_path, front_text_path)
        extract_text(back_path, back_text_path)
        result["ocr"] = True
    except Exception as e:
        result["errors"].append(f"{front_path.name} OCR: {e}")

    # Date verification (LLM visual cross-check)
    if ollama_available and result["ocr"]:
        try:
            for txt_path, img_path in [(front_text_path, front_path), (back_text_path, back_path)]:
                corrections = verify_dates(img_path, txt_path, conflicts_dir)
                for c in corrections:
                    result["verify_corrections"] += 1
                    result["date_fixes"].append(f"date fix ({img_path.name}): {c}")
        except Exception as e:
            result["errors"].append(f"{front_path.name} date verify: {e}")

    # LLM Interpretation
    if ollama_available and result["ocr"]:
        json_output_path = json_dir / f"{front_path.stem}.json"
        try:
            interpret_text(front_text_path, back_text_path, json_output_path, prompt_template)
            result["interpreted"] = True
        except Exception as e:
            result["errors"].append(f"{front_path.name} interpret: {e}")

    return result


def extract_all(
    pairs: list[tuple[Path, Path]],
    text_dir: Path,
    json_dir: Path,
    conflicts_dir: Path,
    prompt_template: str | None,
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(
                _extract_one, front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, prompt_template,
            ): front_path.name
            for front_path, back_path in to_process
        }

        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            result = future.result()

            for fix in result["date_fixes"]:
                print(f"        {fix}")

            pair_ok = not result["errors"]
            name = result["front_name"]
            if pair_ok:
                print(f"  [{completed:>{width}}/{total}] {name}  OK")
            else:
                print(f"  [{completed:>{width}}/{total}] {name}  ERROR")

            text_count += result["ocr"]
            verify_count += result["verify_corrections"]
            interpret_count += result["interpreted"]
            all_errors.extend(result["errors"])

    return text_count, verify_count, interpret_count, skipped, total, all_errors
