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


def _make_gemini_client(config_path: Path) -> genai.Client:
    """Create a Gemini client from the config file."""
    config = json.loads(config_path.read_text())
    return genai.Client(api_key=config["gemini_api_key"])


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

            if conflicts_dir:
                conflicts_dir.mkdir(exist_ok=True)
                stem = image_path.stem
                conflict_path = conflicts_dir / f"{stem}_ocr{entry['ocr_year']}_llm{llm_year}.png"
                crop.save(conflict_path)

    if corrections:
        text_path.write_text(text)

    return corrections


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
