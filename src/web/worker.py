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
