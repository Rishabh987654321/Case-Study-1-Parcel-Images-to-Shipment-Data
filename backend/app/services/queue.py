"""DB-backed queue coordinating image processing (docs/architecture.md section 6).

All claim/advance operations are plain functions taking a `Session` - there is
exactly one caller in this app (the worker pool's coordinator thread, see
worker.py), so true multi-writer races can't happen today, but claim_next still
uses an atomic compare-and-swap UPDATE so it stays correct if that ever changes
(e.g. multiple app instances sharing one DB).
"""
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Batch, Image, Result
from app.pipeline.types import ResultRecord

logger = logging.getLogger("app.queue")

_TERMINAL_IMAGE_STATES = ("done", "error")
_IDLE_AUTOCOMPLETE_SECONDS = 300  # docs/architecture.md: idle 5 minutes with no finalize


def _now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue(db: Session, image_id: str) -> None:
    """Uploaded -> queued. A no-op if the image is already queued/past that point."""
    db.execute(update(Image).where(Image.image_id == image_id, Image.status == "uploaded").values(status="queued", updated_at=_now()))
    db.commit()


def claim_next(db: Session) -> Image | None:
    """Atomically claim one queued image from a non-cancelled batch, oldest upload first."""
    candidate_id = db.scalar(
        select(Image.image_id)
        .join(Batch, Batch.batch_id == Image.batch_id)
        .where(Image.status == "queued", Batch.status != "cancelled")
        .order_by(Image.upload_order)
        .limit(1)
    )
    if candidate_id is None:
        return None

    result = db.execute(
        update(Image).where(Image.image_id == candidate_id, Image.status == "queued").values(status="processing", claimed_at=_now(), updated_at=_now())
    )
    db.commit()
    if result.rowcount == 0:
        return None  # another caller won the race; try again next loop tick
    return db.get(Image, candidate_id)


def _result_kwargs_from_record(record: ResultRecord) -> dict:
    evidence = asdict(record.evidence)
    return {
        "status": record.status,
        "primary_flag": record.primary_flag,
        "flag_reason": record.flag_reason,
        "warnings": json.dumps(record.warnings),
        "awb": record.awb,
        "awb_suggestion": record.awb_suggestion,
        "awb_source": record.awb_source,
        "awb_confidence": record.awb_confidence,
        "weight_kg": record.weight_kg,
        "weight_raw": record.weight_raw,
        "length_cm": record.length_cm,
        "width_cm": record.width_cm,
        "height_cm": record.height_cm,
        "dimensions_raw": record.dimensions_raw,
        "courier": record.courier,
        "confidence": record.confidence,
        "evidence": json.dumps(evidence, default=str),
        "pipeline_version": record.pipeline_version,
        "processing_ms": record.processing_ms,
        "processed_at": record.processed_at,
    }


def mark_done(db: Session, image_id: str, record: ResultRecord) -> None:
    image = db.get(Image, image_id)
    if image is None or image.status != "processing":
        return  # stale completion (e.g. after a timeout already marked it error) - ignore
    image.status = "done" if record.status != "ERROR" else "error"
    image.updated_at = _now()

    existing = db.get(Result, image_id)
    kwargs = _result_kwargs_from_record(record)
    if existing is None:
        db.add(Result(image_id=image_id, **kwargs))
    else:
        for key, value in kwargs.items():
            setattr(existing, key, value)

    batch = db.get(Batch, image.batch_id)
    if image.status == "done":
        batch.processed += 1
    else:
        batch.error_count += 1
    batch.updated_at = _now()
    db.commit()
    _maybe_advance_batch_status(db, image.batch_id)


def mark_error(db: Session, image_id: str, error_message: str, flag: str = "PROCESSING_ERROR") -> None:
    image = db.get(Image, image_id)
    if image is None or image.status != "processing":
        return  # stale timeout/exception for an image already resolved - ignore
    image.status = "error"
    image.attempts += 1
    image.updated_at = _now()

    kwargs = {
        "status": "ERROR",
        "primary_flag": flag,
        "flag_reason": error_message,
        "warnings": "[]",
        "awb": None, "awb_suggestion": None, "awb_source": None, "awb_confidence": None,
        "weight_kg": None, "weight_raw": None, "length_cm": None, "width_cm": None, "height_cm": None,
        "dimensions_raw": None, "courier": None, "confidence": 0.0, "evidence": "{}",
        "pipeline_version": "", "processing_ms": 0, "processed_at": _now(),
    }
    existing = db.get(Result, image_id)
    if existing is None:
        db.add(Result(image_id=image_id, **kwargs))
    else:
        for key, value in kwargs.items():
            setattr(existing, key, value)

    batch = db.get(Batch, image.batch_id)
    batch.error_count += 1
    batch.updated_at = _now()
    db.commit()
    _maybe_advance_batch_status(db, image.batch_id)


def requeue_failed(db: Session, batch_id: str) -> int:
    error_images = db.scalars(select(Image).where(Image.batch_id == batch_id, Image.status == "error")).all()
    for image in error_images:
        image.status = "queued"
        image.claimed_at = None
        image.updated_at = _now()
    batch = db.get(Batch, batch_id)
    if error_images and batch is not None:
        batch.error_count -= len(error_images)
        if batch.status in ("completed", "completed_with_errors"):
            batch.status = "processing"
        batch.updated_at = _now()
    db.commit()
    return len(error_images)


def cancel_batch(db: Session, batch_id: str) -> None:
    batch = db.get(Batch, batch_id)
    if batch is not None and batch.status != "cancelled":
        batch.status = "cancelled"
        batch.updated_at = _now()
        db.commit()


def recover_stuck_images(db: Session) -> int:
    """Startup recovery: images left in 'processing' by a previous crash go back
    to 'queued' (docs/architecture.md: 'On startup, images stuck in processing
    go back to queued')."""
    result = db.execute(update(Image).where(Image.status == "processing").values(status="queued", claimed_at=None, updated_at=_now()))
    db.commit()
    if result.rowcount:
        logger.info("Startup recovery: requeued %d image(s) stuck in 'processing'.", result.rowcount)
    return result.rowcount


def _maybe_advance_batch_status(db: Session, batch_id: str) -> None:
    batch = db.get(Batch, batch_id)
    if batch is None or batch.status == "cancelled":
        return
    remaining = db.scalar(select(Image.image_id).where(Image.batch_id == batch_id, Image.status.not_in(_TERMINAL_IMAGE_STATES)).limit(1))
    if remaining is not None:
        return  # still work in flight

    new_status = "completed_with_errors" if batch.error_count > 0 else "completed"
    if batch.status != new_status:
        batch.status = new_status
        batch.updated_at = _now()
        db.commit()
        _apply_duplicate_awb_warnings(db, batch_id)


def maybe_autocomplete_idle_batch(db: Session, batch: Batch) -> Batch:
    """docs/architecture.md: a batch with all images terminal, idle 5 minutes,
    and never finalized is reported as completed when read."""
    if batch.finalized or batch.status in ("completed", "completed_with_errors", "cancelled"):
        return batch
    if batch.total_images == 0:
        return batch
    remaining = db.scalar(select(Image.image_id).where(Image.batch_id == batch.batch_id, Image.status.not_in(_TERMINAL_IMAGE_STATES)).limit(1))
    if remaining is not None:
        return batch
    idle_seconds = (datetime.now(UTC) - datetime.fromisoformat(batch.updated_at)).total_seconds()
    if idle_seconds < _IDLE_AUTOCOMPLETE_SECONDS:
        return batch
    batch.status = "completed_with_errors" if batch.error_count > 0 else "completed"
    batch.updated_at = _now()
    db.commit()
    _apply_duplicate_awb_warnings(db, batch.batch_id)
    return batch


def _apply_duplicate_awb_warnings(db: Session, batch_id: str) -> None:
    """Post-batch check (docs/architecture.md): same AWB on two OK images in the
    batch adds a DUPLICATE_AWB warning to both. Warning only - never changes OK
    to FLAGGED."""
    ok_results = db.execute(
        select(Result).join(Image, Image.image_id == Result.image_id).where(Image.batch_id == batch_id, Result.status == "OK", Result.awb.is_not(None))
    ).scalars().all()

    by_awb: dict[str, list[Result]] = {}
    for result in ok_results:
        by_awb.setdefault(result.awb, []).append(result)

    changed = False
    for results in by_awb.values():
        if len(results) < 2:
            continue
        for result in results:
            warnings = json.loads(result.warnings or "[]")
            if "DUPLICATE_AWB" not in warnings:
                warnings.append("DUPLICATE_AWB")
                result.warnings = json.dumps(warnings)
                changed = True
    if changed:
        db.commit()
