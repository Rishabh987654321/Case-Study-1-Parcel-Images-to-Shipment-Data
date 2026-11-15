"""Result/record query endpoints."""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import BatchNotFoundError, ImageNotFoundError
from app.models import Batch, Image, Result
from app.schemas import PaginatedRecords, ResultDetail, ResultRecord

router = APIRouter(tags=["records"])

_SORT_COLUMNS = {
    "upload_order": Image.upload_order,
    "status": Result.status,
    "awb": Result.awb,
}


def _dimensions_cm(result: Result) -> dict[str, float] | None:
    if result.length_cm is None and result.width_cm is None and result.height_cm is None:
        return None
    return {"length": result.length_cm, "width": result.width_cm, "height": result.height_cm}


def _to_record(image: Image, result: Result | None) -> ResultRecord:
    if result is None:
        return ResultRecord(
            image_id=image.image_id,
            image_name=image.original_name,
            status="PENDING",
            primary_flag=None,
            flag_reason=None,
            warnings=[],
            awb=None,
            awb_source=None,
            awb_confidence=None,
            awb_suggestion=None,
            weight_kg=None,
            weight_raw=None,
            dimensions_cm=None,
            dimensions_raw=None,
            courier=None,
            confidence=0.0,
            processing_ms=0,
            thumbnail_url=f"/api/images/{image.image_id}/thumbnail",
        )
    return ResultRecord(
        image_id=image.image_id,
        image_name=image.original_name,
        status=result.status,
        primary_flag=result.primary_flag,
        flag_reason=result.flag_reason,
        warnings=json.loads(result.warnings or "[]"),
        awb=result.awb,
        awb_source=result.awb_source,
        awb_confidence=result.awb_confidence,
        awb_suggestion=result.awb_suggestion,
        weight_kg=result.weight_kg,
        weight_raw=result.weight_raw,
        dimensions_cm=_dimensions_cm(result),
        dimensions_raw=result.dimensions_raw,
        courier=result.courier,
        confidence=result.confidence,
        processing_ms=result.processing_ms,
        thumbnail_url=f"/api/images/{image.image_id}/thumbnail",
    )


@router.get("/batches/{batch_id}/records", response_model=PaginatedRecords)
def list_records(
    batch_id: str,
    status: str | None = Query(None),
    flag: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("upload_order"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> PaginatedRecords:
    if db.get(Batch, batch_id) is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})

    stmt = select(Image).outerjoin(Result, Result.image_id == Image.image_id).where(Image.batch_id == batch_id)
    if status:
        stmt = stmt.where(Result.status == status)
    if flag:
        stmt = stmt.where(Result.primary_flag == flag)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Result.awb.like(like), Result.awb_suggestion.like(like), Image.original_name.like(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_col = _SORT_COLUMNS.get(sort, Image.upload_order)
    stmt = stmt.order_by(order_col).offset((page - 1) * page_size).limit(page_size)
    images = db.scalars(stmt).all()

    items = []
    for image in images:
        result = db.get(Result, image.image_id)
        items.append(_to_record(image, result))

    return PaginatedRecords(items=items, page=page, page_size=page_size, total=total)


@router.get("/batches/{batch_id}/records/{image_id}", response_model=ResultDetail)
def get_record(batch_id: str, image_id: str, db: Session = Depends(get_db)) -> ResultDetail:
    if db.get(Batch, batch_id) is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})
    image = db.scalar(select(Image).where(Image.image_id == image_id, Image.batch_id == batch_id))
    if image is None:
        raise ImageNotFoundError(f"Image {image_id} does not exist in this batch.", details={"image_id": image_id})

    result = db.get(Result, image_id)
    record = _to_record(image, result)
    evidence = json.loads(result.evidence) if result and result.evidence else {}
    return ResultDetail(**record.model_dump(), evidence=evidence, image_url=f"/api/images/{image_id}/original")
