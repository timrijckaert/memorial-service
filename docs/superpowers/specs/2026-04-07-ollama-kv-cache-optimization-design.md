# Ollama KV Cache Optimization

## Problem

Each card extraction sends the full prompt (~5KB of static instructions + card text) as a single `user` message to Ollama. Ollama re-evaluates the entire prompt from scratch for every card. With 4 concurrent workers, the model constantly swaps context between cards, preventing any KV cache reuse. As the card volume grows, this becomes a bottleneck.

## Solution

Split the prompt into a `system` message (static instructions) and a `user` message (card text only). Ollama caches the KV state of the system message prefix — when consecutive cards share the same system message, it skips re-evaluation of those tokens. Process cards sequentially so each card benefits from the previous card's cached system prefix.

## Changes

### 1. Split prompt file

Replace `prompts/extract_person.txt` with two files:

**`prompts/extract_person_system.txt`** — Static instructions (lines 1-109 of current file):
- Genealogy extraction role and rules
- Bidprentje structure explanation
- Date/place/spouse extraction rules
- Known places list
- Archaic month names
- Common OCR misspellings

**`prompts/extract_person_user.txt`** — Card text template:
```
--- FRONT TEXT ---
{front_text}

--- BACK TEXT ---
{back_text}
```

### 2. Update `interpret_text` in `src/extract.py`

Change the function signature to accept two prompt strings (`system_prompt` and `user_template`) instead of one `prompt_template`.

Send to Ollama as two messages:
```python
ollama.chat(
    model=MODEL,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ],
    format=PERSON_SCHEMA,
    options={"temperature": 0, "num_predict": 2048},
    keep_alive="30m",
)
```

### 3. Add `keep_alive` to date verification calls

In `verify_dates`, add `keep_alive="30m"` to the `ollama.chat` call to keep the model loaded between date checks.

### 4. Sequential processing in `extract_all`

Replace `ThreadPoolExecutor(max_workers=4)` with a simple `for` loop. Sequential processing ensures every card benefits from the cached system prompt KV state.

### 5. Sequential processing in `ExtractionWorker._run` (server.py)

The web UI's `ExtractionWorker._run` already processes cards sequentially in a `for` loop — no structural change needed. Update it to pass both prompt strings through.

### 6. Update callers

Both `src/main.py` and `src/server.py` load the prompt file. Update them to:
- Load `extract_person_system.txt` and `extract_person_user.txt` separately
- Pass both strings through to `extract_all` / `_extract_one` / `interpret_text`

### 7. Delete `prompts/extract_person.txt`

Remove the old combined prompt file.

## Files affected

| File | Action |
|------|--------|
| `prompts/extract_person_system.txt` | Create — static system instructions |
| `prompts/extract_person_user.txt` | Create — card text template |
| `prompts/extract_person.txt` | Delete |
| `src/extract.py` | Update — split messages, keep_alive, sequential processing |
| `src/main.py` | Update — load two prompt files instead of one |
| `src/server.py` | Update — load two prompt files, pass through to worker |

## Expected impact

- KV cache reuse on the ~5KB system prompt across all cards in a batch
- No model unloading between cards (keep_alive)
- No concurrent context thrashing (sequential LLM calls)
- Zero accuracy change — same model, same instructions, same temperature
