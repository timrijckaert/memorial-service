# OCR Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 4-stage OCR pipeline (Tesseract → date verification → text LLM) with a 2-stage vision+text pipeline (vision model reads images → text model structures JSON).

**Architecture:** The vision model (Qwen2.5-VL 3B) reads front + back card images in a single call, producing a raw text transcription. The text model (Gemma 3 4B) then takes that transcription and produces guaranteed-valid structured JSON via `json_schema` constrained decoding. This removes Tesseract, date verification, intermediate text files, and the async producer/consumer worker pattern.

**Tech Stack:** Python 3, mlx-lm, mlx-vlm, Pillow, stdlib HTTP server

---

### Task 1: Create the vision prompt file

**Files:**
- Create: `prompts/vision_read.txt`

- [ ] **Step 1: Create the vision prompt file**

```text
You are a document reading assistant specialized in Belgian memorial cards (bidprentjes).

ABOUT BIDPRINTJES (memorial cards):
Belgian memorial cards typically follow this structure:
- FRONT: Often contains a prayer, with the deceased's name at the top. Below the name there may be birth/death details.
- BACK: A prayer text, sometimes repeating the deceased's name and dates. The back often contains the most complete biographical information (birth place, death place, spouse, parents, age).
- The deceased's name is most reliably found at the beginning of the biographical text or repeated on the back of the card.
- IGNORE printer marks at the bottom of the card (drukker), e.g. "Drukk. A. Redant en zoon", "Drukkerij Dacquin", "Imp. Vande Velde" — not biographical information.
- IGNORE all religious text: prayers, "Bid voor de ziel van", indulgence references (e.g. "100 d. afl."), saint invocations, Bible verses, and any other devotional content. Only extract biographical facts.

YOUR TASK:
Read the memorial card images and transcribe ALL biographical information you find. Report exactly what you see, preserving the original spellings (even archaic or regional Dutch). Include:
- Full name of the deceased
- Birth date and place
- Death date and place
- Age at death (if explicitly stated)
- Spouse name(s) and the keywords used (echtgenoot/echtgenote/weduwnaar/weduwe)
- Parent references (zoon van / dochter van) — include so the structuring model can distinguish them from spouses
- Any other biographical details

Output plain text only. Do not structure as JSON. Do not interpret or correct — just faithfully report what the card says.

KNOWN PLACES (Arrondissement Aalst, Oost-Vlaanderen, Belgium):
- Haaltert
- Denderhoutem
- Heldergem
- Kerksken
- Terjoden
- Aalst
- Baardegem
- Erembodegem
- Gijzegem
- Herdersem
- Hofstade
- Meldert
- Moorsel
- Nieuwerkerken
- Denderleeuw
- Iddergem
- Erpe-Mere
- Aaigem
- Bambrugge
- Burst
- Erondegem
- Erpe
- Mere
- Ottergem
- Vlekkem
- Herzele
- Borsbeke
- Hillegem
- Ressegem
- Sint-Antelinks
- Sint-Lievens-Esse
- Lede
- Impe
- Oordegem
- Smetlede
- Wanzele
- Ninove
- Zottegem
- Geraardsbergen
- Dendermonde
- Welle
- Lemberge
- Liedekerke

ARCHAIC / REGIONAL DUTCH MONTH NAMES:
Some memorial cards use old Dutch or regional month names. Recognize these when reading:
- Louwmaand / Loumaand = Januari (January)
- Sprokkelmaand = Februari (February)
- Lentemaand, Meert = Maart (March)
- Grasmaand = April
- Bloeimaand = Mei (May)
- Zomermaand / Weidemaand = Juni (June)
- Hooimaand = Juli (July)
- Oogst / Oogstmaand = Augustus (August)
- Herfstmaand / Gerstmaand = September
- Wijnmaand = Oktober (October)
- Slachtmaand = November
- Wintermaand = December
- Op allerheiligen = 1 November
- Op allerzielen = 2 November
```

- [ ] **Step 2: Verify the file exists**

Run: `cat prompts/vision_read.txt | head -5`
Expected: "You are a document reading assistant specialized in Belgian memorial cards"

- [ ] **Step 3: Commit**

```bash
git add prompts/vision_read.txt
git commit -m "feat: add vision model prompt for direct card reading"
```

---

### Task 2: Update the text model system prompt

**Files:**
- Modify: `prompts/extract_person_system.txt:3`

- [ ] **Step 1: Update the OCR reference line**

In `prompts/extract_person_system.txt`, replace line 3:

```
The text was extracted via OCR and may contain errors.
```

with:

```
The text was transcribed from card images by a vision model and may contain errors or omissions.
```

- [ ] **Step 2: Verify the change**

Run: `head -3 prompts/extract_person_system.txt`
Expected: Third line reads "The text was transcribed from card images by a vision model and may contain errors or omissions."

- [ ] **Step 3: Commit**

```bash
git add prompts/extract_person_system.txt
git commit -m "feat: update system prompt for vision model transcription input"
```

---

### Task 3: Update LLMBackend to accept multiple images

**Files:**
- Modify: `src/extraction/llm.py:37-60` (protocol), `src/extraction/llm.py:138-169` (generate_vision)
- Modify: `tests/test_llm.py:90-109` (vision test)

- [ ] **Step 1: Write the failing test**

In `tests/test_llm.py`, add a new test after `test_generate_vision_returns_string`:

```python
@requires_models
def test_generate_vision_accepts_multiple_images(backend):
    """generate_vision accepts a list of images and returns a non-empty string."""
    image1 = _make_number_image("1923")
    image2 = _make_number_image("1945")
    result = backend.generate_vision(
        prompt="Read the numbers in these images. Reply with ONLY the numbers, nothing else.",
        images=[image1, image2],
        temperature=0.0,
        max_tokens=32,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_llm.py::test_generate_vision_accepts_multiple_images -v`
Expected: FAIL — `generate_vision()` does not accept `images` keyword argument

- [ ] **Step 3: Update the LLMBackend protocol**

In `src/extraction/llm.py`, replace the `generate_vision` method in the `LLMBackend` protocol:

```python
class LLMBackend(Protocol):
    """Minimal interface expected by the extraction pipeline."""

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Generate a text response given system and user prompts."""
        ...

    def generate_vision(
        self,
        prompt: str,
        images: list,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate a text response from a prompt and one or more PIL images."""
        ...
```

- [ ] **Step 4: Update MLXBackend.generate_vision to accept a list of images**

Replace the `generate_vision` method in `MLXBackend`:

```python
    def generate_vision(
        self,
        prompt: str,
        images: list,
        temperature: float,
        max_tokens: int,
    ) -> str:
        self._ensure_vision_model()

        image_paths = []
        try:
            for img in images:
                f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                img.save(f, format="PNG")
                f.close()
                image_paths.append(f.name)

            formatted_prompt = mlx_vlm_apply_chat_template(
                self._vision_processor,
                self._vision_config,
                prompt,
                num_images=len(images),
            )

            result = mlx_vlm_generate(
                self._vision_model,
                self._vision_processor,
                formatted_prompt,
                image=image_paths,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return result.text
        finally:
            for p in image_paths:
                os.unlink(p)
```

- [ ] **Step 5: Update existing vision test to use new signature**

In `tests/test_llm.py`, update `test_generate_vision_returns_string`:

```python
@requires_models
def test_generate_vision_returns_string(backend):
    """generate_vision returns a non-empty string from a real image."""
    image = _make_number_image("1923")
    result = backend.generate_vision(
        prompt="Read the number in this image. Reply with ONLY the number, nothing else.",
        images=[image],
        temperature=0.0,
        max_tokens=16,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0
```

- [ ] **Step 6: Run all LLM tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: All tests PASS (integration tests may be skipped if models not downloaded)

- [ ] **Step 7: Commit**

```bash
git add src/extraction/llm.py tests/test_llm.py
git commit -m "feat: update generate_vision to accept multiple images"
```

---

### Task 4: Rewrite interpretation to accept transcription string

**Files:**
- Modify: `src/extraction/interpretation.py`
- Modify: `tests/test_interpret.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/test_interpret.py` entirely with:

```python
# tests/test_interpret.py
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.extraction.interpretation import interpret_transcription
from src.extraction.schema import PERSON_SCHEMA


SAMPLE_LLM_RESPONSE = json.dumps({
    "person": {
        "first_name": "Dominicus",
        "last_name": "Meganck",
        "birth_date": "1813-12-18",
        "birth_place": "Kerksken",
        "death_date": "1913-12-21",
        "death_place": "Kerksken",
        "age_at_death": None,
        "spouses": ["Amelia Gees"]
    },
    "notes": [
        "birth_place OCR reads 'Kerkxken', normalized to 'Kerksken'",
        "Both birth and death dates are explicit, age_at_death left null"
    ]
})

SYSTEM_PROMPT = "You are a genealogy extraction assistant."


def test_interpret_transcription_creates_json_file(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck geboren 1813 Kerksken",
        output, SYSTEM_PROMPT, backend,
        front_image_file="card.jpeg", back_image_file="card 1.jpeg",
    )

    assert output.exists()


def test_interpret_transcription_json_has_required_keys(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Test text", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert "person" in result
    assert "notes" in result
    assert "source" in result


def test_interpret_transcription_sends_transcription_as_user_prompt(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck geboren te Kerkxken",
        output, SYSTEM_PROMPT, backend,
    )

    user_message = backend.generate_text.call_args.args[1]
    assert "Dominicus Meganck geboren te Kerkxken" in user_message


def test_interpret_transcription_passes_json_schema(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Test text", output, SYSTEM_PROMPT, backend,
    )

    assert backend.generate_text.call_args.kwargs["json_schema"] == PERSON_SCHEMA


def test_interpret_transcription_invalid_json_raises(tmp_path):
    backend = MagicMock()
    backend.generate_text.return_value = "not valid json at all"
    output = tmp_path / "card.json"

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        interpret_transcription(
            "Test text", output, SYSTEM_PROMPT, backend,
        )


def test_interpret_transcription_title_cases_uppercase_names(tmp_path):
    """LLM sometimes returns ALL-CAPS names; these must be title-cased."""
    uppercase_response = json.dumps({
        "person": {
            "first_name": "MARIA JOSEPHA",
            "last_name": "VAN DEN BRUELLE",
            "birth_date": "1880-05-14",
            "birth_place": "Haaltert",
            "death_date": "1950-01-03",
            "death_place": "Haaltert",
            "age_at_death": None,
            "spouses": ["JOSEPHUS VAN DE VELDE"]
        },
        "notes": []
    })
    backend = MagicMock()
    backend.generate_text.return_value = uppercase_response
    output = tmp_path / "card.json"

    interpret_transcription(
        "MARIA JOSEPHA VAN DEN BRUELLE", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert result["person"]["first_name"] == "Maria Josepha"
    assert result["person"]["last_name"] == "Van Den Bruelle"
    assert result["person"]["spouses"] == ["Josephus Van De Velde"]


def test_interpret_transcription_merges_into_existing_skeleton(tmp_path):
    """When output file already exists (skeleton), merge person/notes into it."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    skeleton = {
        "source": {
            "front_image_file": "scan_047.jpeg",
            "back_image_file": "scan_047_verso.jpeg",
        }
    }
    output.write_text(json.dumps(skeleton))

    interpret_transcription(
        "Dominicus Meganck geboren 1813",
        output, SYSTEM_PROMPT, backend,
        front_image_file="scan_047.jpeg",
        back_image_file="scan_047_verso.jpeg",
    )

    result = json.loads(output.read_text())
    assert result["person"]["first_name"] == "Dominicus"
    assert len(result["notes"]) > 0
    assert result["source"]["front_image_file"] == "scan_047.jpeg"
    assert result["source"]["back_image_file"] == "scan_047_verso.jpeg"


def test_interpret_transcription_derives_locality(tmp_path):
    """interpret_transcription should derive locality from death_place/birth_place."""
    backend = MagicMock()
    backend.generate_text.return_value = SAMPLE_LLM_RESPONSE
    output = tmp_path / "card.json"

    interpret_transcription(
        "Dominicus Meganck", output, SYSTEM_PROMPT, backend,
    )

    result = json.loads(output.read_text())
    assert result["person"]["locality"] == "Kerksken"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_interpret.py -v`
Expected: FAIL — `interpret_transcription` does not exist

- [ ] **Step 3: Rewrite interpretation.py**

Replace `src/extraction/interpretation.py` entirely:

```python
# src/extraction/interpretation.py
"""LLM-based structuring of vision transcriptions into biographical data."""

import json
from pathlib import Path

from src.extraction.llm import LLMBackend
from src.extraction.schema import PERSON_SCHEMA
from src.locality import derive_locality


def interpret_transcription(
    transcription: str,
    output_path: Path,
    system_prompt: str,
    backend: LLMBackend,
    front_image_file: str | None = None,
    back_image_file: str | None = None,
) -> None:
    """Structure a vision-model transcription into JSON using the text LLM.

    Sends the system prompt and transcription to the backend with
    json_schema for constrained decoding. Writes the parsed JSON to
    output_path. Raises on failure (caller handles).
    """
    response_text = backend.generate_text(
        system_prompt, transcription,
        temperature=0, max_tokens=2048,
        json_schema=PERSON_SCHEMA,
    )

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {response_text[:200]}"
        ) from e

    # Title-case names — LLM sometimes passes through ALL-CAPS from the card
    person = result.get("person", {})
    for field in ("first_name", "last_name"):
        if isinstance(person.get(field), str):
            person[field] = person[field].title()
    if isinstance(person.get("spouses"), list):
        person["spouses"] = [
            s.title() if isinstance(s, str) else s for s in person["spouses"]
        ]

    # Derive locality for filename
    person["locality"] = derive_locality(result)

    # Read existing file (skeleton from match phase) if present
    existing = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text())

    # Merge extracted data into existing structure
    existing["person"] = result.get("person", {})
    existing["notes"] = result.get("notes", [])
    existing_source = existing.get("source", {})
    if front_image_file is not None:
        existing_source["front_image_file"] = front_image_file
    if back_image_file is not None:
        existing_source["back_image_file"] = back_image_file
    existing["source"] = existing_source

    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_interpret.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/extraction/interpretation.py tests/test_interpret.py
git commit -m "feat: rewrite interpretation to accept vision transcription string"
```

---

### Task 5: Rewrite the extraction pipeline

**Files:**
- Modify: `src/extraction/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_pipeline.py` entirely:

```python
# tests/test_pipeline.py
"""Tests for the 2-stage extraction pipeline."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from src.extraction.pipeline import extract_one, ExtractionResult


def _make_test_image(path: Path) -> Path:
    """Create a minimal test image."""
    img = Image.new("RGB", (100, 50), "white")
    img.save(path, "JPEG")
    return path


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_calls_vision_then_text(mock_interpret, tmp_path):
    """Pipeline calls vision read then text structuring in order."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Dominicus Meganck geboren 1813"

    steps = []
    result = extract_one(
        front, back, json_dir,
        mock_backend, "system prompt", "vision prompt",
        on_step=lambda s: steps.append(s),
    )

    assert steps == ["vision_read", "text_extract"]
    assert mock_backend.generate_vision.call_count == 1
    assert mock_interpret.call_count == 1
    assert result.interpreted is True
    assert result.errors == []


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_sends_both_images(mock_interpret, tmp_path):
    """Vision model receives both front and back images."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"

    extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    call_args = mock_backend.generate_vision.call_args
    images = call_args.kwargs.get("images") or call_args.args[1]
    assert len(images) == 2


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_single_sided_card(mock_interpret, tmp_path):
    """Single-sided cards send only one image."""
    front = _make_test_image(tmp_path / "card.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"

    result = extract_one(front, None, json_dir, mock_backend, "sys", "vis")

    call_args = mock_backend.generate_vision.call_args
    images = call_args.kwargs.get("images") or call_args.args[1]
    assert len(images) == 1
    assert result.interpreted is True


def test_extract_one_skips_without_backend(tmp_path):
    """Without a backend, nothing runs."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    steps = []
    result = extract_one(
        front, back, json_dir,
        None, None, None,
        on_step=lambda s: steps.append(s),
    )

    assert steps == []
    assert result.interpreted is False


def test_extract_one_reports_vision_error(tmp_path):
    """If vision read fails, the error is captured and text extract is skipped."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.side_effect = RuntimeError("model crashed")

    result = extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    assert len(result.errors) == 1
    assert "vision" in result.errors[0].lower()
    assert result.interpreted is False


@patch("src.extraction.pipeline.interpret_transcription")
def test_extract_one_reports_interpret_error(mock_interpret, tmp_path):
    """If text structuring fails, the error is captured."""
    front = _make_test_image(tmp_path / "card.jpeg")
    back = _make_test_image(tmp_path / "card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    mock_backend = MagicMock()
    mock_backend.generate_vision.return_value = "Some text"
    mock_interpret.side_effect = ValueError("bad json")

    result = extract_one(front, back, json_dir, mock_backend, "sys", "vis")

    assert len(result.errors) == 1
    assert "interpret" in result.errors[0].lower()
    assert result.interpreted is False


def test_extraction_result_defaults():
    """ExtractionResult has sensible defaults."""
    result = ExtractionResult(front_name="test.jpeg")

    assert result.front_name == "test.jpeg"
    assert result.interpreted is False
    assert result.errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `extract_one` has wrong signature

- [ ] **Step 3: Rewrite pipeline.py**

Replace `src/extraction/pipeline.py` entirely:

```python
# src/extraction/pipeline.py
"""Orchestrates the full extraction pipeline for a single card pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from src.extraction.llm import LLMBackend
from src.extraction.interpretation import interpret_transcription


@dataclass
class ExtractionResult:
    """Result of processing a single card pair through the extraction pipeline."""
    front_name: str
    interpreted: bool = False
    errors: list[str] = field(default_factory=list)


def extract_one(
    front_path: Path,
    back_path: Path | None,
    json_dir: Path,
    backend: LLMBackend | None,
    system_prompt: str | None,
    vision_prompt: str | None,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    """Process extraction for a single pair: vision read, then text structuring.

    Pipeline stages (reported via on_step callback):
      1. vision_read   — Vision model reads card images
      2. text_extract  — Text model structures transcription into JSON

    Both stages only run if a backend is provided.
    """
    result = ExtractionResult(front_name=front_path.name)

    if not backend:
        return result

    # Stage 1: Vision read
    if on_step:
        on_step("vision_read")
    try:
        images = [Image.open(front_path)]
        if back_path:
            images.append(Image.open(back_path))

        transcription = backend.generate_vision(
            prompt=vision_prompt,
            images=images,
            temperature=0,
            max_tokens=2048,
        )
    except Exception as e:
        result.errors.append(f"{front_path.name} vision read: {e}")
        return result

    # Stage 2: Text structuring
    if on_step:
        on_step("text_extract")
    json_output_path = json_dir / f"{front_path.stem}.json"
    try:
        interpret_transcription(
            transcription, json_output_path,
            system_prompt, backend,
            front_image_file=front_path.name,
            back_image_file=back_path.name if back_path else None,
        )
        result.interpreted = True
    except Exception as e:
        result.errors.append(f"{front_path.name} interpret: {e}")

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/extraction/pipeline.py tests/test_pipeline.py
git commit -m "feat: rewrite pipeline to 2-stage vision read + text structure"
```

---

### Task 6: Simplify the extraction worker

**Files:**
- Modify: `src/web/worker.py`
- Modify: `tests/test_worker.py`

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_worker.py` entirely:

```python
# tests/test_worker.py
"""Tests for the ExtractionWorker sequential pipeline."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from src.web.worker import ExtractionWorker, ExtractionStatus, CardError, CardProgress


def _make_test_image(path: Path) -> Path:
    """Create a minimal test image."""
    img = Image.new("RGB", (100, 50), "white")
    img.save(path, "JPEG")
    return path


def test_extraction_status_to_dict():
    """ExtractionStatus.to_dict() produces a JSON-serializable dict."""
    status = ExtractionStatus(
        status="running",
        in_flight=[CardProgress("card1", "vision_read")],
        done=["card0"],
        errors=[CardError("card3", "failed")],
        queue=["card4"],
    )
    d = status.to_dict()
    assert d["status"] == "running"
    assert d["in_flight"] == [{"card_id": "card1", "stage": "vision_read"}]
    assert d["done"] == ["card0"]
    assert d["errors"] == [{"card_id": "card3", "reason": "failed"}]
    assert d["queue"] == ["card4"]


def test_worker_starts_idle():
    """New worker starts in idle status."""
    worker = ExtractionWorker()
    status = worker.get_status()
    assert status.status == "idle"
    assert status.in_flight == []
    assert status.done == []
    assert status.errors == []
    assert status.queue == []


@patch("src.web.worker.interpret_transcription")
def test_worker_processes_card(mock_interpret, tmp_path):
    """Worker processes a card through vision read and text extract."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    backend = MagicMock()
    backend.generate_vision.return_value = "Dominicus Meganck"

    worker = ExtractionWorker()
    started = worker.start(
        [("test-uuid-001", front, back)], json_dir,
        "system prompt", "vision prompt", backend,
    )
    assert started is True

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "test-uuid-001" in status.done
    assert backend.generate_vision.call_count == 1
    assert mock_interpret.call_count == 1


def test_worker_reports_vision_errors(tmp_path):
    """Cards with vision read failures go to errors."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    backend = MagicMock()
    backend.generate_vision.side_effect = RuntimeError("model crashed")

    worker = ExtractionWorker()
    worker.start(
        [("err-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert len(status.errors) == 1
    assert status.errors[0].card_id == "err-uuid"
    assert status.done == []


def test_worker_skips_without_backend(tmp_path):
    """Without a backend, cards go straight to done."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    worker = ExtractionWorker()
    worker.start(
        [("no-llm-uuid", front, back)], json_dir,
        None, None, None,
    )

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert "no-llm-uuid" in status.done


def test_worker_rejects_double_start(tmp_path):
    """Starting while already running returns False."""
    front = _make_test_image(tmp_path / "Card.jpeg")
    back = _make_test_image(tmp_path / "Card 1.jpeg")
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    def slow_vision(*args, **kwargs):
        time.sleep(1)
        return "text"

    backend = MagicMock()
    backend.generate_vision.side_effect = slow_vision

    worker = ExtractionWorker()
    worker.start(
        [("dbl-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )
    second = worker.start(
        [("dbl-uuid", front, back)], json_dir,
        "sys", "vis", backend,
    )

    assert second is False


@patch("src.web.worker.interpret_transcription")
def test_worker_cancellation(mock_interpret, tmp_path):
    """Cancelling stops processing after the current card."""
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = _make_test_image(tmp_path / f"{name}.jpeg")
        back = _make_test_image(tmp_path / f"{name} 1.jpeg")
        pairs.append((f"cancel-{name}", front, back))

    def slow_vision(*args, **kwargs):
        time.sleep(0.5)
        return "text"

    backend = MagicMock()
    backend.generate_vision.side_effect = slow_vision

    worker = ExtractionWorker()
    worker.start(pairs, json_dir, "sys", "vis", backend)
    time.sleep(0.3)
    worker.cancel()

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status in ("idle", "cancelled"):
            break

    assert status.status in ("idle", "cancelled")
    total_processed = len(status.done) + len(status.errors)
    assert total_processed < 3


@patch("src.web.worker.interpret_transcription")
def test_worker_processes_multiple_cards(mock_interpret, tmp_path):
    """All cards in a batch are processed."""
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    pairs = []
    for name in ["Card A", "Card B", "Card C"]:
        front = _make_test_image(tmp_path / f"{name}.jpeg")
        back = _make_test_image(tmp_path / f"{name} 1.jpeg")
        pairs.append((f"multi-{name}", front, back))

    backend = MagicMock()
    backend.generate_vision.return_value = "Some text"

    worker = ExtractionWorker()
    worker.start(pairs, json_dir, "sys", "vis", backend)

    for _ in range(50):
        time.sleep(0.1)
        status = worker.get_status()
        if status.status == "idle":
            break

    assert status.status == "idle"
    assert sorted(status.done) == sorted(["multi-Card A", "multi-Card B", "multi-Card C"])
    assert backend.generate_vision.call_count == 3
    assert mock_interpret.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`
Expected: FAIL — `worker.start()` has wrong signature

- [ ] **Step 3: Rewrite worker.py**

Replace `src/web/worker.py` entirely:

```python
# src/web/worker.py
"""Background extraction worker using sequential vision+text pipeline."""

import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from src.extraction.interpretation import interpret_transcription
from src.extraction.llm import LLMBackend


@dataclass
class CardError:
    """An error that occurred during extraction of a single card."""
    card_id: str
    reason: str


@dataclass
class CardProgress:
    """Tracks a single in-flight card and its current stage."""
    card_id: str
    stage: str  # "vision_read" | "text_extract"


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    in_flight: list[CardProgress] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ExtractionWorker:
    """Runs extraction via sequential vision+text pipeline on a background thread.

    For each card:
      1. Vision model reads front + back images → raw transcription
      2. Text model structures transcription → JSON with constrained decoding
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status = ExtractionStatus(status="idle")
        self._cancel = threading.Event()

    def get_status(self) -> ExtractionStatus:
        with self._lock:
            return ExtractionStatus(
                status=self._status.status,
                in_flight=[
                    CardProgress(p.card_id, p.stage)
                    for p in self._status.in_flight
                ],
                done=list(self._status.done),
                errors=[
                    CardError(e.card_id, e.reason)
                    for e in self._status.errors
                ],
                queue=list(self._status.queue),
            )

    def start(
        self,
        pairs: list[tuple[str, Path, Path | None]],
        json_dir: Path,
        system_prompt: str | None,
        vision_prompt: str | None,
        backend: LLMBackend | None,
    ) -> bool:
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [card_id for card_id, _, _ in pairs]
            self._status = ExtractionStatus(
                status="running", queue=queue_names,
            )

        self._cancel.clear()
        thread = threading.Thread(
            target=self._run,
            args=(pairs, json_dir, system_prompt, vision_prompt, backend),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"
        self._cancel.set()

    def _run(self, pairs, json_dir, system_prompt, vision_prompt, backend):
        for card_id, front_path, back_path in pairs:
            if self._cancel.is_set():
                break

            with self._lock:
                if card_id in self._status.queue:
                    self._status.queue.remove(card_id)

            if not backend:
                with self._lock:
                    self._status.done.append(card_id)
                continue

            # Stage 1: Vision read
            with self._lock:
                self._status.in_flight = [CardProgress(card_id, "vision_read")]

            try:
                images = [Image.open(front_path)]
                if back_path:
                    images.append(Image.open(back_path))

                transcription = backend.generate_vision(
                    prompt=vision_prompt,
                    images=images,
                    temperature=0,
                    max_tokens=2048,
                )
            except Exception as e:
                with self._lock:
                    self._status.in_flight = []
                    self._status.errors.append(
                        CardError(card_id, f"vision read: {e}")
                    )
                continue

            if self._cancel.is_set():
                break

            # Stage 2: Text structuring
            with self._lock:
                self._status.in_flight = [CardProgress(card_id, "text_extract")]

            json_output_path = json_dir / f"{card_id}.json"
            try:
                interpret_transcription(
                    transcription, json_output_path,
                    system_prompt, backend,
                    front_image_file=front_path.name,
                    back_image_file=back_path.name if back_path else None,
                )
            except Exception as e:
                with self._lock:
                    self._status.in_flight = []
                    self._status.errors.append(
                        CardError(card_id, f"interpret: {e}")
                    )
                continue

            with self._lock:
                self._status.in_flight = []
                self._status.done.append(card_id)

        with self._lock:
            if self._cancel.is_set():
                self._status.status = "cancelled"
            else:
                self._status.status = "idle"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_worker.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/worker.py tests/test_worker.py
git commit -m "feat: simplify worker to sequential vision+text loop"
```

---

### Task 7: Update server.py to match new worker interface

**Files:**
- Modify: `src/web/server.py:195-230`

- [ ] **Step 1: Update the extract endpoint in server.py**

In `src/web/server.py`, replace the extract endpoint block (lines ~195-230). Find this block:

```python
            text_dir = output_dir / "text"
            text_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)
            conflicts_dir = output_dir / "date_conflicts"

            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            user_template_path = prompts_dir / "extract_person_user.txt"
            system_prompt = None
            user_template = None
            if system_prompt_path.exists() and user_template_path.exists():
                system_prompt = system_prompt_path.read_text()
                user_template = user_template_path.read_text()

            backend = self.server.backend if system_prompt else None

            started = self.server.worker.start(
                all_items, text_dir, json_dir, conflicts_dir,
                system_prompt, user_template, backend,
            )
```

Replace with:

```python
            json_dir.mkdir(exist_ok=True)

            # Load prompt files
            prompts_dir = input_dir.parent / "prompts"
            system_prompt_path = prompts_dir / "extract_person_system.txt"
            vision_prompt_path = prompts_dir / "vision_read.txt"
            system_prompt = None
            vision_prompt = None
            if system_prompt_path.exists() and vision_prompt_path.exists():
                system_prompt = system_prompt_path.read_text()
                vision_prompt = vision_prompt_path.read_text()

            backend = self.server.backend if system_prompt else None

            started = self.server.worker.start(
                all_items, json_dir,
                system_prompt, vision_prompt, backend,
            )
```

- [ ] **Step 2: Run the server test to verify it still works**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/web/server.py
git commit -m "feat: update server extract endpoint for vision+text pipeline"
```

---

### Task 8: Delete OCR and date verification code and tests

**Files:**
- Delete: `src/extraction/ocr.py`
- Delete: `src/extraction/date_verification.py`
- Delete: `tests/test_ocr.py`
- Delete: `tests/test_verify_dates.py`
- Delete: `prompts/extract_person_user.txt`
- Modify: `requirements.txt:3` (remove pytesseract)

- [ ] **Step 1: Delete the old files**

```bash
rm src/extraction/ocr.py
rm src/extraction/date_verification.py
rm tests/test_ocr.py
rm tests/test_verify_dates.py
rm prompts/extract_person_user.txt
```

- [ ] **Step 2: Remove pytesseract from requirements.txt**

Edit `requirements.txt` — remove the line `pytesseract>=0.3.10`. The file should become:

```
Pillow>=10.0
pytest>=8.0
mlx-lm
mlx-vlm
torch
torchvision
```

- [ ] **Step 3: Update extraction package __init__.py**

Replace `src/extraction/__init__.py`:

```python
# src/extraction/__init__.py
"""Extraction pipeline for memorial card digitization.

Public API:
    extract_one  — Run the 2-stage vision+text pipeline for one card pair
    make_backend — Create an LLM backend from config
    LLMBackend   — LLM backend abstraction
    PERSON_SCHEMA — JSON schema for structured extraction output
"""

from src.extraction.pipeline import extract_one, ExtractionResult
from src.extraction.llm import make_backend, LLMBackend
from src.extraction.schema import PERSON_SCHEMA

__all__ = ["extract_one", "ExtractionResult", "make_backend", "LLMBackend", "PERSON_SCHEMA"]
```

- [ ] **Step 4: Run the full test suite to verify nothing is broken**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS. No import errors for deleted modules.

- [ ] **Step 5: Commit**

```bash
git add -u
git add requirements.txt src/extraction/__init__.py
git commit -m "chore: remove Tesseract OCR, date verification, and pytesseract dependency"
```

---

### Task 9: Update documentation

**Files:**
- Modify: `docs/ai/overview.md`

- [ ] **Step 1: Update overview.md**

Replace the Pipeline and Tech Stack sections in `docs/ai/overview.md`:

```markdown
## Pipeline

The application runs a 3-phase workflow via a browser-based UI:

1. **Match** — Scans the `input/` directory, fuzzy-matches front/back image pairs by filename similarity, and presents them for manual confirmation. Each confirmed pair gets a UUID.

2. **Extract** — Runs a 2-stage pipeline:
   - **Vision read:** A vision model (Qwen2.5-VL 3B via mlx-vlm) reads both card images directly, producing a raw text transcription of biographical content.
   - **Text structure:** A text model (Gemma 3 4B via mlx-lm) takes the transcription and produces structured JSON via constrained decoding (`json_schema`), extracting names, dates, places, and spouses.

3. **Review** — Shows extracted data in a form for human correction. Handles title-casing, date validation, age-at-death calculation, and spouse management.

4. **Export** — Stitches front+back images side-by-side and writes all cards to a consolidated `memorial_cards.json` with derived Dutch-convention filenames.

## Tech Stack

- **Backend:** Python 3, stdlib HTTP server (`http.server`), no frameworks
- **Frontend:** Vanilla JavaScript, single `index.html`, no build tools
- **Vision model:** Qwen2.5-VL 3B via `mlx-vlm` — reads card images directly
- **Text model:** Gemma 3 4B via `mlx-lm` — structures transcription into JSON with constrained decoding
- **Image processing:** Pillow for stitching and image loading
```

Leave the Scraper and Target Usage sections unchanged.

- [ ] **Step 2: Verify the auto-generated docs rebuild**

Run: `.venv/bin/python docs/ai/rebuild.py`
Expected: "Updated" messages or "Knowledge base is up to date."

- [ ] **Step 3: Commit**

```bash
git add docs/ai/overview.md docs/ai/architecture.md docs/ai/api-surface.md docs/ai/data-model.md
git commit -m "docs: update pipeline description for vision+text architecture"
```

---

## Task Dependency Order

```
Task 1 (vision prompt) ─────────────────────────────────────────┐
Task 2 (system prompt) ─────────────────────────────────────────┤
Task 3 (LLM backend multi-image) ──→ Task 5 (pipeline) ────────┤
Task 4 (interpretation rewrite) ──→ Task 5 (pipeline) ──→ Task 6 (worker) ──→ Task 7 (server) ──→ Task 8 (cleanup) ──→ Task 9 (docs)
```

Tasks 1, 2, 3, and 4 can run in parallel. Tasks 5-9 are sequential.
