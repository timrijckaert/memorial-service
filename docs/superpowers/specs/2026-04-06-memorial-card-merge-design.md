# Memorial Card Processor — Phase 1: Merge & Export

## Problem

Digitize a collection of ~50-200 Belgian memorial cards (bidprentjes). Each card has a front (portrait photo) and back (biographical/prayer text) scanned as separate JPEG files. Phase 1 merges each pair into a single side-by-side image.

## Constraints

- macOS (Apple Silicon or Intel), no admin access assumed
- Zero global installs — fully self-contained in project folder
- Python 3 + Pillow in a local venv
- Future phases (auto-crop, OCR) will build on this foundation

## Project Structure

```
memorial-service/
├── run.sh                  # Entry point — sets up venv, runs the script
├── requirements.txt        # Pillow
├── src/
│   └── merge.py            # Stitching logic
├── input/                  # Drop front + back scan pairs here
├── output/                 # Stitched JPGs written here
└── docs/
```

- `input/` and `output/` are gitignored (large, personal images)

## Filename Convention

Scans follow this naming pattern:

- **Front (photo):** `Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg`
- **Back (text):** `Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928 1.jpeg`

The back scan has ` 1` appended before the file extension. The front scan is the base name without this suffix.

## Pairing Logic

1. List all `.jpeg`/`.jpg` files in `input/`
2. Identify back scans: files matching `* 1.jpeg` (or `.jpg`)
3. For each back scan, derive the front filename by removing ` 1` before the extension
4. If the front file exists: valid pair
5. Missing front or missing back: report as error, skip the card
6. Both sides are always expected — a missing side is always an error

Output filename: the front scan's filename, written to `output/`.

## Stitching Logic

For each valid pair:

1. Load both images with Pillow
2. If heights differ: scale the shorter image to match the taller one's height, preserving aspect ratio
3. Create a new canvas: width = front width + back width, height = max height, white background
4. Paste front on the left (x=0), back on the right (x=front width), flush — no gap
5. Export as JPEG to `output/` at 85% quality

Layout: **photo (front) on the left, text (back) on the right**.

## run.sh Wrapper

1. Check Python 3 is available; exit with helpful message if not
2. Create `.venv/` if it doesn't exist
3. Install `requirements.txt` into venv (only on first run / if needed)
4. Run `src/merge.py`

The user only ever runs: `./run.sh`

## Console Output

```
Found 87 pairs in input/
[  1/87] Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg  OK
[  2/87] De Smet Maria Theresia Aalst  bidprentje 3 maart 1945.jpeg  OK
...
[ 45/87] Pieters Jan Baptist Gent  bidprentje 12 juni 1912.jpeg  ERROR: missing back scan

Done: 86 merged, 1 error
```

Errors are shown inline and summarized at the end.

## Error Handling

| Scenario | Behavior |
|---|---|
| Front exists, back missing | Report error, skip card |
| Back exists, front missing | Report error, skip card |
| Corrupt/unreadable image | Report error with filename, skip card |
| `input/` directory empty | Print message, exit cleanly |
| `input/` directory missing | Create it, print message, exit cleanly |
| Output file already exists | Overwrite silently |

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3 | Ships with macOS, great ecosystem for image/OCR work |
| Isolation | `venv` | Built-in, no global installs |
| Image processing | Pillow | Battle-tested, simple API for stitching |
| Entry point | `run.sh` | Automates venv setup, single command to run |

## Future Phases (out of scope, informing decisions)

- **Phase 2 — Auto-crop:** Detect card edges on A4 flatbed scans, crop and straighten. Likely adds OpenCV or scikit-image.
- **Phase 3 — OCR:** Extract name, birth/death dates, birthplace from Dutch-language text. Likely adds pytesseract or Claude Vision API. Export to CSV/JSON.

The project structure and Python/venv foundation are chosen to support these additions without restructuring.
