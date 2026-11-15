"""CSV export. Column order and set per the Phase 3 task (supersedes the earlier
Phase 2 list in docs/data_model.md section 3, which has been updated to match -
see that doc for the note on what changed and why)."""
import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.errors import BatchNotFoundError, BatchNotReadyError
from app.models import Batch, Image, Result

router = APIRouter(tags=["export"])

CSV_COLUMNS = [
    "image_name", "status", "primary_flag", "flag_reason", "awb", "awb_suggestion",
    "awb_source", "awb_confidence", "weight_kg", "weight_raw", "length_cm", "width_cm",
    "height_cm", "dimensions_raw", "warnings", "processed_at", "pipeline_version", "image_id",
]
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _row_for(image: Image, result: Result | None) -> list[str]:
    if result is None:
        return [_csv_safe(image.original_name), _csv_safe("PENDING")] + [""] * 14 + [_csv_safe(image.image_id)]

    warnings = ";".join(json.loads(result.warnings or "[]"))
    return [
        _csv_safe(image.original_name),
        _csv_safe(result.status),
        _csv_safe(result.primary_flag or ""),
        _csv_safe(result.flag_reason or ""),
        _csv_safe(result.awb or ""),
        _csv_safe(result.awb_suggestion or ""),
        _csv_safe(result.awb_source or ""),
        _csv_safe(f"{result.awb_confidence:.2f}" if result.awb_confidence is not None else ""),
        _csv_safe(result.weight_kg if result.weight_kg is not None else ""),
        _csv_safe(result.weight_raw or ""),
        _csv_safe(result.length_cm if result.length_cm is not None else ""),
        _csv_safe(result.width_cm if result.width_cm is not None else ""),
        _csv_safe(result.height_cm if result.height_cm is not None else ""),
        _csv_safe(result.dimensions_raw or ""),
        _csv_safe(warnings),
        _csv_safe(result.processed_at),
        _csv_safe(result.pipeline_version),
        _csv_safe(image.image_id),
    ]


def _stream_csv(batch_id: str, only: str) -> Iterator[bytes]:
    """Opens its own DB session rather than reusing the request's Depends(get_db)
    one: FastAPI tears that down based on the endpoint function returning, which
    happens as soon as the StreamingResponse object is constructed - well before
    this generator has finished iterating."""
    yield b"\xef\xbb\xbf"  # UTF-8 BOM
    buf = io.StringIO()
    csv.writer(buf).writerow(CSV_COLUMNS)
    yield buf.getvalue().encode("utf-8")

    db = SessionLocal()
    try:
        images = db.scalars(select(Image).where(Image.batch_id == batch_id).order_by(Image.upload_order)).all()
        for image in images:
            result = db.get(Result, image.image_id)
            if only == "ok" and (result is None or result.status != "OK"):
                continue
            if only == "flagged" and (result is None or result.status not in ("FLAGGED", "ERROR")):
                continue
            buf = io.StringIO()
            csv.writer(buf).writerow(_row_for(image, result))
            yield buf.getvalue().encode("utf-8")
    finally:
        db.close()


@router.get("/batches/{batch_id}/export.csv")
def export_csv(batch_id: str, only: str = Query("all", pattern="^(all|ok|flagged)$"), db: Session = Depends(get_db)) -> StreamingResponse:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})

    result_count = db.scalar(select(func.count()).select_from(Result).join(Image, Image.image_id == Result.image_id).where(Image.batch_id == batch_id)) or 0
    if result_count == 0:
        raise BatchNotReadyError("There are no results to download yet.")

    filename = f"parcel_results_{batch_id}_{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        _stream_csv(batch_id, only),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batches/{batch_id}/export-rejected.csv")
def export_rejected_csv(batch_id: str, db: Session = Depends(get_db)) -> None:
    if db.get(Batch, batch_id) is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})
    # Rejected uploads are not persisted (docs/api.md marks this endpoint optional);
    # the per-request accepted/rejected response from POST .../images is the only record.
    raise HTTPException(status_code=404, detail="Rejected-uploads export is not implemented; see the upload response's rejected[] array instead.")
