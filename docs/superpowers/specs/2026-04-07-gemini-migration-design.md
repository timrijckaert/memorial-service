# Gemini API Migration

## Problem

Local LLM inference via Ollama takes 3-10s per card for token generation, which is the bottleneck when processing many cards. Google Gemini's free tier offers 1M tokens/day with sub-second generation — fast enough to process thousands of cards at no cost.

## Solution

Replace Ollama with the Google Gemini API (`google-genai` SDK) for both text interpretation and date verification. Store the API key in a local config file.

## Changes

### 1. Config file

Create `config.json` at project root (gitignored):

```json
{
  "gemini_api_key": "AIzaSyCRCqfcYe0FbIZjHOljgZVp3M3CPx-bHvs"
}
```

Add `config.json` to `.gitignore`.

### 2. Replace Ollama with Gemini in `src/extract.py`

**Remove:**
- `import ollama`
- `MODEL` constant
- All `ollama.chat()` calls
- `keep_alive` parameter

**Add:**
- `from google import genai`
- Load config and create Gemini client
- Model: `gemini-2.0-flash`

**`interpret_text`** — Replace `ollama.chat` with:
```python
client.models.generate_content(
    model="gemini-2.0-flash",
    config=genai.types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0,
        max_output_tokens=2048,
        response_mime_type="application/json",
        response_schema=PERSON_SCHEMA,
    ),
    contents=user_message,
)
```

**`verify_dates`** — Replace `ollama.chat` with a Gemini vision call. Upload the cropped year image and ask the model to read it. Gemini accepts PIL images or file bytes directly.

### 3. Update dependencies

**`requirements.txt`:**
- Remove: `ollama`
- Add: `google-genai`

### 4. Update `src/main.py`

- Remove: `import ollama`, Ollama reachability check (`ollama.list()`)
- Add: config file loading, check for API key presence
- Pass API key availability instead of `ollama_available`

### 5. Update `src/server.py`

- Remove: Ollama import and reachability check in POST `/api/extract`
- Add: config file loading, check for API key
- Update error message from "Ollama is not running" to "Gemini API key not configured"

### 6. Update `run.sh`

- Remove: Ollama checks (command exists, service running, model pull)
- Add: check for `config.json` and `google-genai` pip package

### 7. Structured output schema

The Gemini SDK uses a slightly different schema format than Ollama's JSON schema. The existing `PERSON_SCHEMA` may need minor adjustments to match Gemini's `response_schema` expectations (Gemini uses a subset of OpenAPI 3.0 schema).

## Files affected

| File | Action |
|------|--------|
| `config.json` | Create — API key storage (gitignored) |
| `.gitignore` | Update — add config.json |
| `src/extract.py` | Update — replace Ollama with Gemini SDK |
| `src/main.py` | Update — config loading, remove Ollama checks |
| `src/server.py` | Update — config loading, remove Ollama checks |
| `requirements.txt` | Update — swap ollama for google-genai |
| `run.sh` | Update — remove Ollama checks, add config check |

## Expected impact

- Generation time: 3-10s → sub-second per card
- Cost: free (Gemini free tier: 1M tokens/day)
- Accuracy: Gemini 2.0 Flash should match or exceed Gemma 4 on structured extraction
- No more dependency on running Ollama locally
