# Async Pipeline: Parallel OCR + Sequential LLM

**Date:** 2026-04-07
**Status:** Draft

## Goal

Speed up card extraction by running OCR in parallel across cards (and front/back within a card) while keeping LLM calls sequential. Rewrite the worker to use `asyncio` with a two-stage producer-consumer pipeline.

## Current Behavior

- Cards are processed one at a time in a `for` loop on a single daemon thread
- Within each card: OCR front -> OCR back -> date verify -> LLM interpret (all sequential)
- Status tracks a single `current` card

## Architecture

```
                    +---------------------------+
                    |     asyncio event loop     |
                    |    (1 background thread)   |
                    |                            |
  pairs -->  +------+-------+  asyncio.Queue  +--+----------+
             |  OCR stage   | --------------> |  LLM stage  |
             |  (executor)  |                 |  (serial)   |
             +--------------+                 +-------------+
                    |                              |
                    |  front + back OCR            |  date_verify
                    |  via run_in_executor         |  interpret
                    |  (multiple cards at once)    |  (one card at a time)
                    +------------------------------+
```

The entire event loop runs on a single daemon thread, keeping the existing synchronous HTTP server unchanged.

## OCR Stage (Producer)

- One async coroutine per card, all launched concurrently via `asyncio.gather`
- Each coroutine runs front + back Tesseract OCR in parallel using `loop.run_in_executor()`
- `ThreadPoolExecutor(max_workers=4)` bounds concurrency — enough to keep Tesseract busy without thrashing CPU
- On completion, each coroutine pushes result data onto an `asyncio.Queue`
- After all OCR tasks complete, a `None` sentinel is pushed to signal the LLM consumer to stop

```python
async def ocr_card(front_path, back_path, text_dir, executor, ocr_queue):
    loop = asyncio.get_event_loop()
    front_text_path = text_dir / f"{front_path.stem}_front.txt"
    back_text_path = text_dir / f"{back_path.stem}_back.txt"
    await asyncio.gather(
        loop.run_in_executor(executor, extract_text, front_path, front_text_path),
        loop.run_in_executor(executor, extract_text, back_path, back_text_path),
    )
    await ocr_queue.put(card_data)
```

## LLM Stage (Consumer)

- Single async coroutine consuming from the `asyncio.Queue`
- Processes one card at a time: date verification, then LLM interpretation
- Uses `httpx.AsyncClient` to call Ollama (non-blocking I/O)
- Stops when it receives the sentinel value

```python
async def llm_consumer(ocr_queue, backend):
    while True:
        card_data = await ocr_queue.get()
        if card_data is None:
            break
        await run_date_verify(card_data, backend)
        await run_interpret(card_data, backend)
```

## Async LLM Backend

The `OllamaBackend` gets an async counterpart with `generate_text` and `generate_vision` as async methods using `httpx.AsyncClient`. A new `AsyncLLMBackend` Protocol sits alongside the existing sync `LLMBackend`. The sync versions remain for any non-pipeline use.

## Status Model

The single-card `current` field is replaced by an `in_flight` list supporting multiple active cards:

```python
@dataclass
class CardProgress:
    card_id: str
    stage: str  # "ocr" | "date_verify" | "llm_extract"

@dataclass
class ExtractionStatus:
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    in_flight: list[CardProgress]  # multiple cards can be active simultaneously
    done: list[str]
    errors: list[CardError]
    queue: list[str]
```

Thread safety: status updates happen on the asyncio event loop thread. The sync HTTP server calls `get_status()` from request threads. A `threading.Lock` guards `_status` (held briefly for snapshot copies).

## UI Changes (app.js)

The extract progress view renders a table of in-flight cards instead of a single current card:

```
Processing 12 cards...

  In progress:
    card_003  > OCR
    card_004  > OCR
    card_002  > date verification

  Done: 4/12
  Errors: 0
  Queue: 5 remaining
```

Polling interval stays at 1500ms. Only the rendering logic changes to iterate over the `in_flight` list.

## Error Handling

- **OCR failure:** Card goes straight to `errors`, never enters the LLM queue. Other cards continue.
- **LLM failure:** Error recorded, consumer moves to next card in queue.
- **Cancellation:** OCR stage stops launching new cards. Running OCR subprocesses finish naturally. LLM consumer finishes its current card then stops. Remaining queued cards are left unprocessed. Status becomes `"cancelled"`.
- **No backend:** OCR runs for all cards, nothing enters the LLM queue. Consumer receives sentinel immediately and exits.

## Executor Lifecycle

The `ThreadPoolExecutor` is created per run and shut down after all OCR tasks complete. No leaked threads between runs.

## Files Changed

| File | Change |
|------|--------|
| `src/web/worker.py` | Rewrite to async two-stage pipeline with `asyncio` event loop on daemon thread |
| `src/extraction/pipeline.py` | Split `extract_one` into `ocr_card` (async) and `llm_card` (async) functions |
| `src/extraction/llm.py` | Add `AsyncLLMBackend` Protocol and `AsyncOllamaBackend` using `httpx.AsyncClient` |
| `src/web/server.py` | Update status endpoint to return `in_flight` instead of `current` |
| `src/web/static/app.js` | Update extract progress UI to show multiple in-flight cards |
| `requirements.txt` / `pyproject.toml` | Add `httpx` dependency |

## New Dependencies

- `httpx` — async HTTP client for Ollama API calls

## Out of Scope

- Migrating the HTTP server itself to async (e.g., aiohttp/FastAPI)
- Card-level LLM parallelism
- Gemini async backend (only Ollama is in use)
