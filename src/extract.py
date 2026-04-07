# src/extract.py
import json
import re
import time
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import pytesseract

_YEAR_RE = re.compile(r"^\d{4}$")

GEMINI_MODEL = "gemini-2.5-flash"

_MAX_RETRIES = 3


def _call_gemini(client: genai.Client, **kwargs):
    """Call Gemini with automatic retry on rate limit (429) errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(**kwargs)
        except ClientError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                wait = 60  # default wait
                print(f"        Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

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


def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Creates the output file even
    if no text is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    raw = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(raw)


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

        resp = _call_gemini(
            client,
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
        if not resp.text:
            continue
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

    response = _call_gemini(
        client,
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
