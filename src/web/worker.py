# src/web/worker.py
"""Background extraction worker using async two-stage pipeline."""

import asyncio
import dataclasses
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.extraction.ocr import extract_text
from src.extraction.date_verification import verify_dates
from src.extraction.interpretation import interpret_text
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
    stage: str  # "ocr" | "date_verify" | "llm_extract"


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


@dataclass
class _OcrResult:
    """Internal data passed from OCR stage to LLM stage."""
    card_name: str
    front_path: Path
    back_path: Path | None
    front_text_path: Path
    back_text_path: Path | None


class ExtractionWorker:
    """Runs extraction via async two-stage pipeline on a background thread.

    Stage 1 (OCR producer): launches all cards' OCR concurrently via
    ThreadPoolExecutor. Front + back OCR run in parallel per card.

    Stage 2 (LLM consumer): pulls OCR-completed cards from an asyncio.Queue
    and runs date verification + interpretation one card at a time.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status = ExtractionStatus(status="idle")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cancel: asyncio.Event | None = None

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
        text_dir: Path,
        json_dir: Path,
        conflicts_dir: Path,
        system_prompt: str | None,
        user_template: str | None,
        backend: LLMBackend | None,
    ) -> bool:
        with self._lock:
            if self._status.status == "running":
                return False
            queue_names = [card_id for card_id, _, _ in pairs]
            self._status = ExtractionStatus(
                status="running", queue=queue_names,
            )

        thread = threading.Thread(
            target=self._run_loop,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        with self._lock:
            if self._status.status == "running":
                self._status.status = "cancelling"
        if self._loop and self._cancel:
            self._loop.call_soon_threadsafe(self._cancel.set)

    def _run_loop(self, pairs, text_dir, json_dir, conflicts_dir,
                  system_prompt, user_template, backend):
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._cancel = None
        try:
            loop.run_until_complete(
                self._run(pairs, text_dir, json_dir, conflicts_dir,
                          system_prompt, user_template, backend)
            )
        finally:
            loop.close()
            self._loop = None
            self._cancel = None

    async def _run(self, pairs, text_dir, json_dir, conflicts_dir,
                   system_prompt, user_template, backend):
        self._cancel = asyncio.Event()
        ocr_queue: asyncio.Queue[_OcrResult | None] = asyncio.Queue()
        executor = ThreadPoolExecutor(max_workers=4)

        try:
            producer = asyncio.create_task(
                self._ocr_producer(pairs, text_dir, ocr_queue, executor)
            )
            consumer = asyncio.create_task(
                self._llm_consumer(
                    ocr_queue, executor, json_dir, conflicts_dir,
                    system_prompt, user_template, backend,
                )
            )
            await asyncio.gather(producer, consumer)
        finally:
            executor.shutdown(wait=False)

        with self._lock:
            if self._cancel.is_set():
                self._status.status = "cancelled"
            else:
                self._status.status = "idle"

    def _remove_in_flight(self, card_name: str):
        """Remove card from in_flight list. Caller must hold self._lock."""
        self._status.in_flight = [
            p for p in self._status.in_flight
            if p.card_id != card_name
        ]

    async def _ocr_producer(self, pairs, text_dir, ocr_queue, executor):
        loop = asyncio.get_running_loop()

        async def ocr_one(card_id: str, front_path: Path, back_path: Path | None):
            card_name = card_id
            if self._cancel.is_set():
                return

            with self._lock:
                if card_name in self._status.queue:
                    self._status.queue.remove(card_name)
                self._status.in_flight.append(
                    CardProgress(card_name, "ocr")
                )

            front_text_path = text_dir / f"{card_id}_front.txt"
            back_text_path = text_dir / f"{card_id}_back.txt" if back_path else None

            try:
                tasks = [
                    loop.run_in_executor(
                        executor, extract_text,
                        front_path, front_text_path,
                    ),
                ]
                if back_path and back_text_path:
                    tasks.append(
                        loop.run_in_executor(
                            executor, extract_text,
                            back_path, back_text_path,
                        ),
                    )
                await asyncio.gather(*tasks)
            except Exception as e:
                with self._lock:
                    self._remove_in_flight(card_name)
                    self._status.errors.append(
                        CardError(card_name, f"OCR: {e}")
                    )
                return

            with self._lock:
                for p in self._status.in_flight:
                    if p.card_id == card_name:
                        p.stage = "waiting"
                        break

            await ocr_queue.put(_OcrResult(
                card_name=card_name,
                front_path=front_path,
                back_path=back_path,
                front_text_path=front_text_path,
                back_text_path=back_text_path,
            ))

        await asyncio.gather(*(ocr_one(cid, f, b) for cid, f, b in pairs))
        await ocr_queue.put(None)  # sentinel

    async def _llm_consumer(self, ocr_queue, executor, json_dir,
                            conflicts_dir, system_prompt, user_template,
                            backend):
        loop = asyncio.get_running_loop()

        while True:
            item = await ocr_queue.get()
            if item is None:
                break

            if self._cancel.is_set():
                with self._lock:
                    self._remove_in_flight(item.card_name)
                continue

            if not backend:
                with self._lock:
                    self._remove_in_flight(item.card_name)
                    self._status.done.append(item.card_name)
                continue

            card_name = item.card_name

            # Date verification
            with self._lock:
                for p in self._status.in_flight:
                    if p.card_id == card_name:
                        p.stage = "date_verify"
                        break

            try:
                verify_items = [(item.front_text_path, item.front_path)]
                if item.back_text_path and item.back_path:
                    verify_items.append((item.back_text_path, item.back_path))
                for txt_path, img_path in verify_items:
                    await loop.run_in_executor(
                        executor, verify_dates,
                        img_path, txt_path, backend, conflicts_dir,
                    )
            except Exception as e:
                with self._lock:
                    self._remove_in_flight(card_name)
                    self._status.errors.append(
                        CardError(card_name, f"date verify: {e}")
                    )
                continue

            # LLM interpretation
            with self._lock:
                for p in self._status.in_flight:
                    if p.card_id == card_name:
                        p.stage = "llm_extract"
                        break

            json_output_path = json_dir / f"{card_name}.json"
            back_text = item.back_text_path if item.back_text_path else item.front_text_path
            try:
                await loop.run_in_executor(
                    executor, interpret_text,
                    item.front_text_path, back_text,
                    json_output_path,
                    system_prompt, user_template, backend,
                    item.front_path.name,
                    item.back_path.name if item.back_path else None,
                )
            except Exception as e:
                with self._lock:
                    self._remove_in_flight(card_name)
                    self._status.errors.append(
                        CardError(card_name, f"interpret: {e}")
                    )
                continue

            with self._lock:
                self._remove_in_flight(card_name)
                self._status.done.append(card_name)
