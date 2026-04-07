# src/merge.py
import json
import os
import re
from pathlib import Path
from PIL import Image
import ollama
import pytesseract

JPEG_EXTENSIONS = {".jpeg", ".jpg"}


def find_pairs(input_dir: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Find front/back pairs in input_dir based on filename convention.

    Back scans have ' 1' before the extension. Front scans are the base name.
    Returns (pairs, errors) where pairs is [(front_path, back_path), ...].
    """
    files = list(input_dir.iterdir())

    jpeg_files = {
        f.name: f
        for f in files
        if f.is_file() and f.suffix.lower() in JPEG_EXTENSIONS
    }

    back_files: dict[str, Path] = {}
    front_files: dict[str, Path] = {}

    for name, path in jpeg_files.items():
        stem = path.stem
        if stem.endswith(" 1"):
            back_files[name] = path
        else:
            front_files[name] = path

    # Build normalized lookup for backs: "stem 1" -> path (using lowercase extension)
    back_lookup: dict[str, Path] = {}
    for name, path in back_files.items():
        normalized_key = f"{path.stem}{path.suffix.lower()}"
        back_lookup[normalized_key] = path

    pairs: list[tuple[Path, Path]] = []
    errors: list[str] = []
    matched_backs: set[str] = set()

    for front_name, front_path in sorted(front_files.items()):
        stem = front_path.stem
        ext_lower = front_path.suffix.lower()
        # Try matching with same extension first, then alternate
        for try_ext in [ext_lower] + [e for e in JPEG_EXTENSIONS if e != ext_lower]:
            normalized_back_key = f"{stem} 1{try_ext}"
            if normalized_back_key in back_lookup:
                back_path = back_lookup[normalized_back_key]
                pairs.append((front_path, back_path))
                matched_backs.add(back_path.name)
                break
        else:
            errors.append(f"{front_name}: missing back scan")

    for back_name in sorted(back_files):
        if back_name not in matched_backs:
            errors.append(f"{back_name}: missing front scan")

    return pairs, errors


def stitch_pair(front_path: Path, back_path: Path, output_path: Path) -> None:
    """Stitch front and back images side-by-side (front left, back right).

    If heights differ, the shorter image is scaled up to match the taller one.
    Output is JPEG at 85% quality.
    """
    front = Image.open(front_path)
    back = Image.open(back_path)

    target_height = max(front.height, back.height)

    if front.height < target_height:
        scale = target_height / front.height
        front = front.resize(
            (round(front.width * scale), target_height), Image.LANCZOS
        )

    if back.height < target_height:
        scale = target_height / back.height
        back = back.resize(
            (round(back.width * scale), target_height), Image.LANCZOS
        )

    canvas = Image.new("RGB", (front.width + back.width, target_height), "white")
    canvas.paste(front, (0, 0))
    canvas.paste(back, (front.width, 0))
    canvas.save(output_path, "JPEG", quality=85)


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


_YEAR_RE = re.compile(r"^\d{4}$")


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

        # Save crop to a temporary file for the LLM
        crop_path = text_path.parent / f"_crop_{entry['ocr_year']}.png"
        crop.save(crop_path)

        try:
            resp = ollama.chat(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": "Read the number in this image. Reply with ONLY the 4-digit year number, nothing else.",
                    "images": [str(crop_path)],
                }],
                options={"temperature": 0},
            )
            llm_year = resp.message.content.strip().rstrip(",.")

            if _YEAR_RE.match(llm_year) and llm_year != entry["ocr_year"]:
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
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}

MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")


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
        options={"temperature": 0},
    )

    result = json.loads(response.message.content)

    result["source"] = {
        "front_text_file": front_text_path.name,
        "back_text_file": back_text_path.name,
    }

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))


def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    text_dir = output_dir / "text"
    json_dir = output_dir / "json"
    conflicts_dir = output_dir / "date_conflicts"
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
        except Exception as e:
            print(f"Warning: Ollama not reachable ({e}) — skipping text interpretation")

    total = len(pairs)
    ok_count = 0
    text_count = 0
    verify_count = 0
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
        ocr_ok = False
        front_text_path = text_dir / f"{front_path.stem}_front.txt"
        back_text_path = text_dir / f"{back_path.stem}_back.txt"
        try:
            extract_text(front_path, front_text_path)
            extract_text(back_path, back_text_path)
            text_count += 1
            ocr_ok = True
        except Exception as e:
            all_errors.append(f"{front_path.name} OCR: {e}")
            pair_ok = False

        # Date verification (LLM visual cross-check)
        if ollama_available and ocr_ok:
            try:
                for txt_path, img_path in [(front_text_path, front_path), (back_text_path, back_path)]:
                    corrections = verify_dates(img_path, txt_path, conflicts_dir)
                    for c in corrections:
                        verify_count += 1
                        print(f"        date fix ({img_path.name}): {c}")
            except Exception as e:
                all_errors.append(f"{front_path.name} date verify: {e}")

        # LLM Interpretation
        if ollama_available and ocr_ok:
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

    print(f"\nDone: {ok_count} merged, {text_count} text extracted, {verify_count} date{'s' if verify_count != 1 else ''} corrected, {interpret_count} interpreted, {len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    if all_errors:
        print(f"\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
