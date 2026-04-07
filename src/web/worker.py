# src/web/worker.py
"""Background extraction worker thread."""

import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path

from src.extraction import extract_one
from src.extraction.llm import LLMBackend


@dataclass
class CardError:
    """An error that occurred during extraction of a single card."""
    card_id: str
    reason: str


@dataclass
class ExtractionStatus:
    """Snapshot of the extraction worker's current state."""
    status: str  # "idle" | "running" | "cancelling" | "cancelled"
    current: dict | None = None
    done: list[str] = field(default_factory=list)
    errors: list[CardError] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)


class ExtractionWorker:
    """Runs extraction sequentially on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._status = ExtractionStatus(status="idle")

    def get_status(self) -> ExtractionStatus:
        """Return a snapshot copy of the current status."""
        with self._lock:
            return ExtractionStatus(
                status=self._status.status,
                current=dict(self._status.current) if self._status.current else None,
                done=list(self._status.done),
                errors=[CardError(e.card_id, e.reason) for e in self._status.errors],
                queue=list(self._status.queue),
            )

    def start(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ) -> bool:
        """Start extraction on a background thread. Returns False if already running."""
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._status = ExtractionStatus(
                status="running",
                queue=queue_names,
            )
            self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        """Signal the worker to stop after the current card."""
        self._cancel.set()
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"

    def _run(
        self,
        pairs: list[tuple[Path, Path]],
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ):
        """Process all pairs sequentially. Runs on a background thread."""
        for front_path, back_path in pairs:
            if self._cancel.is_set():
                with self._lock:
                    self._status.status = "cancelled"
                return

            card_name = front_path.stem

            with self._lock:
                if card_name in self._status.queue:
                    self._status.queue.remove(card_name)
                self._status.current = {"card_id": card_name, "step": "ocr_front"}

            def _on_step(step):
                with self._lock:
                    if self._status.current:
                        self._status.current["step"] = step

            result = extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                backend, system_prompt, user_template,
                on_step=_on_step,
            )

            with self._lock:
                if result.errors:
                    self._status.errors.append(
                        CardError(card_id=card_name, reason="; ".join(result.errors))
                    )
                else:
                    self._status.done.append(card_name)
                self._status.current = None

        with self._lock:
            if self._status.status != "cancelled":
                self._status.status = "idle"
