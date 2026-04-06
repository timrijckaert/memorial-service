# Memorial Card OCR Text Extraction — Design Spec

## Problem

The memorial card processor (Phase 1) already merges front/back scan pairs into stitched images. Now we need to extract the printed text from each scan (front and back separately) and save it as plain text files. This enables future searching, indexing, and structured data extraction from the collection.

## Constraints

- macOS (Apple Silicon or Intel)
- Tesseract installed via Homebrew (`brew install tesseract tesseract-lang`)
- `run.sh` checks for Tesseract and prints install instructions if missing
- Text is mostly Dutch
- OCR must never crash the pipeline — errors are logged and processing continues

## Dependencies

### System

- `tesseract` — open-source OCR engine (installed via `brew install tesseract tesseract-lang`)
- The `tesseract-lang` package provides the Dutch (`nld`) language pack

### Python

- `pytesseract` — Python wrapper for Tesseract (added to `requirements.txt`)
- `Pillow` — already a dependency, used to open images before passing to pytesseract

## OCR Function

**`extract_text(image_path: Path, output_path: Path) -> None`** in `src/merge.py`:

1. Open the image with `Image.open(image_path)`
2. Run `pytesseract.image_to_string(image, lang="nld")` to extract text
3. Strip leading/trailing whitespace from the result
4. Write the text to `output_path` (even if the result is empty)

## Pipeline Integration

The OCR step is added to the existing `main()` flow. Merge and OCR run in a single pass:

1. Find pairs in `input/` (existing)
2. Create `output/` and `output/text/` directories
3. For each matched pair:
   - Stitch front + back into `output/{front_filename}` (existing)
   - Extract text from the front scan → `output/text/{front_stem}_front.txt`
   - Extract text from the back scan → `output/text/{back_stem}_back.txt`
4. If OCR fails on a file, log it as an error but continue processing
5. Print summary at the end

## Output Structure

```
output/
├── Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg
├── text/
│   ├── Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928_front.txt
│   └── Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928 1_back.txt
```

## Output Filename Convention

- Front text file: `{front_scan_stem}_front.txt`
- Back text file: `{back_scan_stem}_back.txt`

Where `stem` is the filename without extension.

## Error Handling

- If Tesseract is not installed: `run.sh` prints install instructions and exits before running Python
- If OCR fails on a single image: log the error, skip that text file, continue with next pair
- If OCR returns empty text: still create the text file (it will be empty)
- OCR errors are collected and printed in the end-of-run summary alongside any merge errors

## Console Output

```
Found 21 pairs in input/
[ 1/21] Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg  OK
[ 2/21] Meganck Dominicus Kerksken bidprentje 21 december 1913.jpeg  OK
...

Done: 21 merged, 21 text extracted, 0 errors
```

## run.sh Update

Add a Tesseract check before the Python invocation:

```bash
if ! command -v tesseract &>/dev/null; then
    echo "Error: tesseract is required but not found."
    echo "Install it with: brew install tesseract tesseract-lang"
    exit 1
fi
```

## Testing

- **Unit test for `extract_text`:** Create a simple image with known text using Pillow, run OCR, verify the output file exists and contains text. Note: Tesseract accuracy on synthetic images may vary, so the test should verify the file is created and non-empty rather than exact text matching.
- **Unit test for error handling:** Verify that a corrupt/unreadable image produces an error message but does not raise an exception.
- **Integration:** Run on actual memorial card scans to verify Dutch text quality.
