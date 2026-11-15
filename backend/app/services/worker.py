"""Background worker pool: claims queued images and runs the Phase 1 pipeline on
them in subprocesses, so a slow/CPU-bound image never blocks the API.

Architecture: one coordinator thread (started from main.py's lifespan) owns a
ProcessPoolExecutor and a dict of in-flight futures. Each loop tick it reaps
anything finished or timed-out, then tops the pool back up to WORKER_COUNT by
claiming more queued images. All DB writes happen on the coordinator thread via
its own session - the worker *subprocesses* only run process_image() and return
a plain picklable dict, they never touch the database (SQLite sessions can't
cross a process boundary).
"""
import dataclasses
import logging
import os
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

from app.db import SessionLocal
from app.models import Image
from app.pipeline.types import ResultRecord
from app.services import queue, storage

logger = logging.getLogger("app.worker")

_POLL_INTERVAL_S = 0.2


def _worker_initializer() -> None:
    """Runs once per subprocess at pool startup. Pins thread pools to 1 so
    WORKER_COUNT processes don't oversubscribe the CPU (see providers/ocr_rapid.py's
    comment: unpinned RapidOCR sessions measured mean OCR time blowing up from
    ~1.5s single-process to ~26s under 8 unpinned worker processes). RapidOCR
    itself is already pinned there; this is defense in depth for OpenCV/BLAS too."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    try:
        import cv2

        cv2.setNumThreads(1)
    except ImportError:
        pass


def _run_pipeline(image_id: str, image_path: str, filename: str) -> dict:
    """Top-level function run in a worker subprocess - must stay picklable
    (no closures/methods) for ProcessPoolExecutor."""
    from app.pipeline.runner import process_image

    record = process_image(image_path, filename, image_id)
    return dataclasses.asdict(record)


class WorkerPool:
    def __init__(self, worker_count: int | None = None, timeout_s: int | None = None):
        # Resolved at call time, not as a default-argument expression, so tests
        # can monkeypatch app.config.WORKER_COUNT/IMAGE_TIMEOUT_S and have a
        # freshly-constructed pool pick it up (default args bind once at import).
        from app import config

        self.worker_count = max(1, worker_count if worker_count is not None else config.WORKER_COUNT)
        self.timeout_s = timeout_s if timeout_s is not None else config.IMAGE_TIMEOUT_S
        self._executor: ProcessPoolExecutor | None = None
        self._in_flight: dict[Future, tuple[str, float]] = {}  # future -> (image_id, submitted_at)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._executor = ProcessPoolExecutor(max_workers=self.worker_count, initializer=_worker_initializer)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="worker-pool-coordinator", daemon=True)
        self._thread.start()
        logger.info("Worker pool started with %d worker(s).", self.worker_count)

    def stop(self, wait_timeout_s: float = 30.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=wait_timeout_s)
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Worker pool stopped.")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._reap_finished_or_timed_out()
            self._top_up()
            time.sleep(_POLL_INTERVAL_S)

    def _reap_finished_or_timed_out(self) -> None:
        now = time.perf_counter()
        for future in list(self._in_flight):
            image_id, submitted_at = self._in_flight[future]
            if future.done():
                del self._in_flight[future]
                self._handle_completed(image_id, future)
            elif now - submitted_at > self.timeout_s:
                del self._in_flight[future]
                db = SessionLocal()
                try:
                    queue.mark_error(db, image_id, f"Processing timed out after {self.timeout_s}s")
                finally:
                    db.close()
                # The subprocess itself is left running rather than killed (killing
                # and restarting a pool worker is expensive); its eventual result is
                # simply dropped here since this image is already marked error. If it
                # finishes and the image gets requeued later, mark_done's own status
                # check ("only apply if still 'processing'") guards against a stale
                # late result ever overwriting that retry.

    def _handle_completed(self, image_id: str, future: Future) -> None:
        db = SessionLocal()
        try:
            try:
                result_dict = future.result()
            except Exception:
                # A crashed/raising worker must not kill the coordinator thread.
                # docs/architecture.md section 9: stack traces go to logs, not
                # responses - the full traceback is logged here, never stored in
                # the record a user can see via the API/CSV.
                logger.exception("Pipeline subprocess failed for image_id=%s", image_id)
                queue.mark_error(db, image_id, "An unexpected error occurred while processing this image.")
                return
            record = _record_from_dict(result_dict)
            queue.mark_done(db, image_id, record)
        finally:
            db.close()

    def _top_up(self) -> None:
        while len(self._in_flight) < self.worker_count:
            db = SessionLocal()
            try:
                image = queue.claim_next(db)
            finally:
                db.close()
            if image is None:
                return
            self._submit(image)

    def _submit(self, image: Image) -> None:
        path = str(Path(storage.get_image_path(image.stored_path)).resolve())
        future = self._executor.submit(_run_pipeline, image.image_id, path, image.original_name)
        self._in_flight[future] = (image.image_id, time.perf_counter())


def _record_from_dict(data: dict) -> ResultRecord:
    """Rebuild the dataclass tree process_image() returned (as a plain dict,
    for safe pickling) so queue.mark_done can reuse its normal field access."""
    from app.pipeline.types import (
        AwbCandidate,
        BarcodeResult,
        LabelRegionInfo,
        OcrLine,
        OverlayData,
        ParsedFields,
        PipelineEvidence,
        QualityMetrics,
        SceneSignals,
    )

    ev = data["evidence"]
    evidence = PipelineEvidence(
        quality=QualityMetrics(**ev["quality"]) if ev.get("quality") else None,
        barcodes=[BarcodeResult(**b) for b in ev.get("barcodes", [])],
        ocr_lines=[OcrLine(**o) for o in ev.get("ocr_lines", [])],
        overlay=OverlayData(**ev["overlay"]) if ev.get("overlay") else OverlayData(),
        label_region=LabelRegionInfo(**ev["label_region"]) if ev.get("label_region") else None,
        awb_candidates=[AwbCandidate(**a) for a in ev.get("awb_candidates", [])],
        parsed_fields=ParsedFields(**ev["parsed_fields"]) if ev.get("parsed_fields") else ParsedFields(),
        scene_signals=SceneSignals(**ev["scene_signals"]) if ev.get("scene_signals") else SceneSignals(),
        timings=ev.get("timings", {}),
        load_error=ev.get("load_error"),
        pipeline_notes=ev.get("pipeline_notes", []),
    )
    data = {**data, "evidence": evidence}
    return ResultRecord(**data)
