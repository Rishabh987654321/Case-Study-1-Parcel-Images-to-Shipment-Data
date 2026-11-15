"""Batch lifecycle endpoints. Background processing (Phase 3) is stubbed here:
finalize moves a batch to "processing" but nothing currently claims images, so
batches stay at "processing" with 0 processed until the worker pool exists.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import WORKER_COUNT
from app.db import get_db
from app.errors import BatchNotFoundError, EmptyUploadError
from app.models import Batch, Image, Result
from app.schemas import (
    BatchCreate,
    BatchSummary,
    CancelResponse,
    FinalizeResponse,
    PaginatedBatches,
    RetryFailedResponse,
)
from app.services import queue

router = APIRouter(tags=["batches"])

_MIN_SAMPLES_FOR_ETA = 3


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _get_batch_or_404(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})
    batch = queue.maybe_autocomplete_idle_batch(db, batch)
    return batch


def _eta_seconds(db: Session, batch: Batch) -> int | None:
    remaining = batch.total_images - batch.processed - batch.error_count
    if remaining <= 0:
        return None
    done_times = db.scalars(
        select(Result.processing_ms).join(Image, Image.image_id == Result.image_id).where(Image.batch_id == batch.batch_id, Result.status != "ERROR")
    ).all()
    if len(done_times) < _MIN_SAMPLES_FOR_ETA:
        return None
    mean_ms = sum(done_times) / len(done_times)
    return round(remaining * mean_ms / 1000.0 / max(1, WORKER_COUNT))


def _summarize(db: Session, batch: Batch) -> BatchSummary:
    counts_rows = db.execute(
        select(Result.status, func.count()).join(Image, Image.image_id == Result.image_id).where(Image.batch_id == batch.batch_id).group_by(Result.status)
    ).all()
    counts = {status: count for status, count in counts_rows}

    flag_rows = db.execute(
        select(Result.primary_flag, func.count())
        .join(Image, Image.image_id == Result.image_id)
        .where(Image.batch_id == batch.batch_id, Result.primary_flag.is_not(None))
        .group_by(Result.primary_flag)
    ).all()
    flag_counts = {flag: count for flag, count in flag_rows}

    done_and_errored = batch.processed + batch.error_count
    progress_pct = round(100.0 * done_and_errored / batch.total_images, 1) if batch.total_images else 0.0

    return BatchSummary(
        batch_id=batch.batch_id,
        name=batch.name,
        status=batch.status,
        finalized=batch.finalized,
        created_at=batch.created_at,
        total_images=batch.total_images,
        rejected_count=batch.rejected_count,
        processed=done_and_errored,
        progress_pct=progress_pct,
        eta_seconds=_eta_seconds(db, batch),
        counts=counts,
        flag_counts=flag_counts,
    )


@router.post("/batches", status_code=201)
def create_batch(body: BatchCreate = BatchCreate(), db: Session = Depends(get_db)) -> dict:
    batch = Batch(
        batch_id=uuid.uuid4().hex,
        name=body.name,
        status="created",
        finalized=False,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(batch)
    db.commit()
    return {"batch_id": batch.batch_id, "status": batch.status}


@router.get("/batches", response_model=PaginatedBatches)
def list_batches(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)) -> PaginatedBatches:
    total = db.scalar(select(func.count()).select_from(Batch)) or 0
    batches = db.scalars(select(Batch).order_by(Batch.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return PaginatedBatches(items=[_summarize(db, b) for b in batches], page=page, page_size=page_size, total=total)


@router.get("/batches/{batch_id}", response_model=BatchSummary)
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchSummary:
    batch = _get_batch_or_404(db, batch_id)
    return _summarize(db, batch)


@router.post("/batches/{batch_id}/finalize", response_model=FinalizeResponse)
def finalize_batch(batch_id: str, db: Session = Depends(get_db)) -> FinalizeResponse:
    batch = _get_batch_or_404(db, batch_id)
    if batch.finalized:
        return FinalizeResponse(status=batch.status)  # idempotent
    if batch.total_images == 0:
        raise EmptyUploadError("No files were received. Choose one or more JPG or PNG images.")
    batch.finalized = True
    # Images enqueue themselves at upload time, so by the time finalize is
    # called everything may already be terminal (small/fast batch) - in that
    # case don't leave it sitting at "processing" with nothing left to claim.
    remaining = db.scalar(select(Image.image_id).where(Image.batch_id == batch_id, Image.status.not_in(("done", "error"))).limit(1))
    if remaining is None:
        batch.status = "completed_with_errors" if batch.error_count > 0 else "completed"
    else:
        batch.status = "processing"
    batch.updated_at = _now()
    db.commit()
    return FinalizeResponse(status=batch.status)


@router.post("/batches/{batch_id}/cancel", response_model=CancelResponse)
def cancel_batch(batch_id: str, db: Session = Depends(get_db)) -> CancelResponse:
    batch = _get_batch_or_404(db, batch_id)
    queue.cancel_batch(db, batch_id)
    db.refresh(batch)
    return CancelResponse(status=batch.status)


@router.post("/batches/{batch_id}/retry-failed", response_model=RetryFailedResponse)
def retry_failed(batch_id: str, db: Session = Depends(get_db)) -> RetryFailedResponse:
    _get_batch_or_404(db, batch_id)
    count = queue.requeue_failed(db, batch_id)
    return RetryFailedResponse(requeued=count)


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch(batch_id: str, db: Session = Depends(get_db)) -> None:
    from app.services.storage import delete_files

    batch = _get_batch_or_404(db, batch_id)
    images = db.scalars(select(Image).where(Image.batch_id == batch_id)).all()
    delete_files([img.stored_path for img in images], [img.thumbnail_path for img in images])
    db.delete(batch)
    db.commit()
