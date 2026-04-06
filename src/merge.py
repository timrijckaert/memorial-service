# src/merge.py
import json
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


def extract_text(image_path: Path, output_path: Path) -> None:
    """Extract text from an image using Tesseract OCR and write to a text file.

    Uses Dutch (nld) language model. Creates the output file even if no text
    is detected. Raises on failure (caller handles).
    """
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang="nld")
    output_path.write_text(text.strip())


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
        except Exception as e:
            print(f"Warning: Ollama not reachable ({e}) — skipping text interpretation")

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

    print(f"\nDone: {ok_count} merged, {text_count} text extracted, {interpret_count} interpreted, {len(all_errors)} error{'s' if len(all_errors) != 1 else ''}")

    if all_errors:
        print(f"\nCould not process:")
        for error in all_errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
