# src/main.py
import argparse
from pathlib import Path
import ollama

from src.merge import find_pairs, merge_all
from src.extract import extract_all
from src.review import start_review


def main() -> None:
    parser = argparse.ArgumentParser(description="Memorial card processing pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["merge", "extract", "all", "review"],
        help="Which phase to run (default: all)",
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
    prompt_path = script_dir / "prompts" / "extract_person.txt"

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

    # --- Review phase ---
    if args.command == "review":
        if not json_dir.exists() or not any(json_dir.glob("*.json")):
            print("No extracted cards found. Run 'extract' first.")
            return
        start_review(json_dir, input_dir)
        return

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
                print(f"Warning: Ollama not reachable ({e}) — skipping LLM steps")

        print("\n--- Extract ---")
        text_count, verify_count, interpret_count, extract_skipped, _, extract_errors = extract_all(
            pairs, text_dir, json_dir, conflicts_dir,
            prompt_template, ollama_available, force=args.force,
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
