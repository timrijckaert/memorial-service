# OCR Removal Design

## Context

A benchmark of 50 scraped heemkring cards (2026-04-19) compared OCR+text-LLM (Tesseract + Gemma 3 4B) vs vision-only (Qwen2.5-VL 3B). Vision-only with a rich prompt scored **80.3% vs 75.0% overall**, winning on dates (84-92% vs 78%) and places (74-90% vs 62-82%). OCR+LLM was slightly better on names (72-78% vs 68-74%).

The conclusion: vision can replace Tesseract for reading cards. But we want to keep the text model's constrained JSON output (`json_schema`) for guaranteed-valid structured data.

## Goal

Replace the 4-stage OCR pipeline with a 2-stage vision+text pipeline. Remove Tesseract entirely while keeping constrained JSON output.

## Architecture

### Current pipeline (4 stages)

```
Front image --> Tesseract OCR --> front.txt --\
                                               +--> Date verification (vision LLM on cropped digits) --> corrected .txt --> Text LLM + json_schema --> JSON
Back image  --> Tesseract OCR --> back.txt --/
```

- Stage 1: Tesseract OCR on front image
- Stage 2: Tesseract OCR on back image
- Stage 3: Date verification — Tesseract bounding boxes + vision LLM cross-check year digits
- Stage 4: Text LLM interpretation — OCR text + system prompt + json_schema --> structured JSON

### New pipeline (2 stages)

```
Front image --\
               +--> Vision model ("read these cards") --> raw transcription --> Text model + json_schema --> JSON
Back image  --/
```

- Stage 1 (vision read): Vision model (Qwen2.5-VL 3B) receives both front and back images in a single call. Outputs a raw text transcription of the biographical content.
- Stage 2 (text structure): Text model (Gemma 3 4B) receives the vision transcription + system prompt with rules + `json_schema` constrained decoding. Outputs guaranteed-valid structured JSON.

### Why two stages instead of one

The vision model (mlx-vlm) does not support `json_schema` constrained decoding. The text model (mlx-lm) does. By splitting reading from structuring, we get:
- The vision model's strength: reading text directly from images (better than Tesseract)
- The text model's strength: producing guaranteed-valid JSON via constrained decoding
- The system prompt's domain rules (aldaar resolution, date ranges, spouse disambiguation, known places, corrections) applied during structuring

## File Changes

### Delete

- `src/extraction/ocr.py` — Tesseract OCR wrapper, replaced by vision model
- `src/extraction/date_verification.py` — year digit cross-checking, no longer needed

### Create

- `prompts/vision_read.txt` — prompt for the vision model, giving it context about what bidprentjes are and instructing it to transcribe all biographical text from the images

### Modify

- `src/extraction/llm.py` — update `generate_vision()` to accept a list of PIL Images (front + back sent together in one call) instead of a single image. Update the `LLMBackend` protocol to match. Keep both models, lazy loading, temp file management, and `generate_text()` with `json_schema` unchanged.

- `src/extraction/interpretation.py` — no longer reads text files. Receives a vision transcription string directly as input. Feeds it to the text model as `user_prompt` with the system prompt and `json_schema`. Title-casing, locality derivation, and JSON merging with the skeleton file stay the same.

- `src/extraction/pipeline.py` — replace 4-stage orchestration with 2 stages: vision read then text structure. The `ExtractionResult` dataclass updates to reflect the new stages (drop `ocr_done`, `verify_corrections`, `date_fixes`). The `extract_one` function simplifies: open both images, call vision model, pass transcription to interpretation.

- `src/web/worker.py` — replace the async producer/consumer pattern (~200 lines of event loop, queue, executor) with a simple sequential loop on a background thread. Keep `ExtractionStatus`, `get_status()`, and `cancel()` — the web UI polls these. Stages reported per card: `"vision_read"` then `"text_extract"` (instead of `"ocr"`, `"date_verify"`, `"llm_extract"`).

- `prompts/extract_person_system.txt` — swap the OCR reference line ("The text was extracted via OCR and may contain errors") for something like "The text was transcribed from card images by a vision model and may contain errors." Everything else stays the same.

- `docs/ai/overview.md` — update the pipeline description from 4 stages to 2 stages and remove Tesseract from the tech stack.

### Unchanged

- `src/web/server.py`, `src/web/static/` — HTTP API and UI unchanged
- `src/matching/`, `src/export/`, `src/locality.py` — unrelated to extraction
- `src/extraction/schema.py` — both model constants (`MLX_TEXT_MODEL`, `MLX_VISION_MODEL`) still needed

## Prompt Files

Two self-contained prompt files, each optimized for its model's task. Shared context (bidprentje description, known places, archaic months) is duplicated in both rather than using a shared include system. This keeps each prompt independent and tunable without risk of breaking the other.

### `prompts/vision_read.txt` (new)

Context about what bidprentjes are (front/back structure, where biographical info typically appears) plus an instruction to transcribe all biographical text from the images. Should include known places and archaic month names to help the vision model recognize ambiguous text. Does NOT include structuring rules, output field descriptions, or JSON formatting — that's the text model's job.

### `prompts/extract_person_system.txt` (modified)

Stays almost identical. Only change: swap the OCR reference line for a vision model reference. All structuring rules, known places, archaic months, mandatory corrections, output field descriptions, and spouse/parent disambiguation rules stay exactly as they are.

## Worker Simplification

The current `ExtractionWorker` uses:
- `asyncio` event loop on a background thread
- `ThreadPoolExecutor` with 4 workers for parallel OCR
- `asyncio.Queue` to feed OCR results to the LLM consumer
- Producer/consumer coroutines with sentinel values

The new worker uses:
- A background thread with a `for card in cards:` loop
- Each iteration: open images, vision read, text structure, write JSON
- Same `ExtractionStatus` dataclass and thread-safe status/cancel interface
- Stages per card: `"vision_read"` then `"text_extract"`

The LLM can only process one card at a time (single GPU), so the parallelism only existed to overlap Tesseract I/O with LLM compute. Without Tesseract, a sequential loop is sufficient.

## Dependencies Removed

- `pytesseract` Python package
- Tesseract system binary (no longer needed on the machine)
- The `output/text/` directory is no longer created or used

## Key Decisions

1. **Two images in one call** — front + back sent together to the vision model. The model sees both sides at once and doesn't need to know which is front vs back.
2. **Two-pass pipeline** — vision reads, text structures. Keeps constrained JSON output.
3. **Two prompt files** — each self-contained with duplicated shared context. No shared includes.
4. **Simple sequential worker** — drop async producer/consumer. One card at a time.
5. **Both models stay** — vision for reading images, text for structuring JSON.
