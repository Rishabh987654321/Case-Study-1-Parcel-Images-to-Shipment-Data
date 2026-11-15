"""Upload and image-serving endpoints."""
from datetime import UTC, datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_FILES_PER_BATCH
from app.db import get_db
from app.errors import (
    BatchFinalizedError,
    BatchNotFoundError,
    EmptyUploadError,
    ImageNotFoundError,
    TooManyFilesError,
)
from app.models import Batch, Image
from app.schemas import UploadAccepted, UploadRejected, UploadResponse
from app.services import queue, storage

router = APIRouter(tags=["images"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_display_name(name: str) -> str:
    """Strip any path components and cap length; never used as a filesystem path."""
    name = (name or "upload").replace("\\", "/").split("/")[-1]
    return name[:255] or "upload"


# Per docs/design.md section 6 message catalogue.
_REJECTION_MESSAGES = {
    "NOT_AN_IMAGE": '"{name}" isn\'t a JPG or PNG image, so it was skipped.',
    "CORRUPT_IMAGE": '"{name}" is damaged and couldn\'t be opened.',
    "FILE_TOO_LARGE": '"{name}" is larger than {max_mb:.0f} MB and was skipped.',
    "IMAGE_TOO_LARGE": '"{name}" has too many pixels to process safely and was skipped.',
    "IMAGE_TOO_SMALL": '"{name}" is smaller than the minimum size and was skipped.',
    "UNSUPPORTED_TYPE": '"{name}" isn\'t a JPG or PNG image, so it was skipped.',
}


def _rejection_message(code: str, name: str) -> str:
    from app.config import MAX_FILE_MB

    template = _REJECTION_MESSAGES.get(code, '"{name}" could not be processed and was skipped.')
    return template.format(name=name, max_mb=MAX_FILE_MB)


@router.post("/batches/{batch_id}/images", response_model=UploadResponse)
async def upload_images(batch_id: str, files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)) -> UploadResponse:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.", details={"batch_id": batch_id})
    if batch.finalized:
        raise BatchFinalizedError("This batch is finalized; no more files can be uploaded to it.")
    if not files:
        raise EmptyUploadError("No files were received. Choose one or more JPG or PNG images.")

    existing_count = db.scalar(select(func.count()).select_from(Image).where(Image.batch_id == batch_id)) or 0
    if existing_count + len(files) > MAX_FILES_PER_BATCH:
        raise TooManyFilesError(
            f"You can upload up to {MAX_FILES_PER_BATCH} images per batch.",
            details={"max_files_per_batch": MAX_FILES_PER_BATCH, "already_uploaded": existing_count},
        )

    next_order = (db.scalar(select(func.max(Image.upload_order)).where(Image.batch_id == batch_id)) or 0) + 1
    accepted: list[UploadAccepted] = []
    rejected: list[UploadRejected] = []

    for upload in files:
        display_name = _safe_display_name(upload.filename or "upload")
        data = await upload.read()
        if not data:
            rejected.append(UploadRejected(name=display_name, code="NOT_AN_IMAGE", message=f'"{display_name}" is empty and could not be read as an image.'))
            continue

        try:
            sha256 = storage.compute_sha256(data)
            existing_row = db.scalar(select(Image).where(Image.batch_id == batch_id, Image.sha256 == sha256))
            warnings: list[str] = []
            if existing_row is not None:
                saved = storage.copy_as_duplicate(
                    storage.SavedImage(
                        image_id=existing_row.image_id,
                        stored_path=existing_row.stored_path,
                        thumbnail_path=existing_row.thumbnail_path,
                        file_size=existing_row.file_size,
                        content_type=existing_row.content_type,
                        sha256=existing_row.sha256,
                        width=existing_row.width,
                        height=existing_row.height,
                    )
                )
                warnings.append("DUPLICATE_IMAGE")
            else:
                saved = storage.save_upload(data)
        except storage.UploadRejection as e:
            rejected.append(UploadRejected(name=display_name, code=e.code, message=_rejection_message(e.code, display_name)))
            continue

        image = Image(
            image_id=saved.image_id,
            batch_id=batch_id,
            original_name=display_name,
            stored_path=saved.stored_path,
            thumbnail_path=saved.thumbnail_path,
            file_size=saved.file_size,
            content_type=saved.content_type,
            sha256=saved.sha256,
            width=saved.width,
            height=saved.height,
            upload_order=next_order,
            status="uploaded",
            created_at=_now(),
            updated_at=_now(),
        )
        next_order += 1
        db.add(image)
        accepted.append(UploadAccepted(image_id=saved.image_id, name=display_name, warnings=warnings))

    batch.total_images += len(accepted)
    batch.rejected_count += len(rejected)
    if batch.status == "created":
        batch.status = "uploading"
    batch.updated_at = _now()
    db.commit()

    for item in accepted:
        queue.enqueue(db, item.image_id)

    return UploadResponse(accepted=accepted, rejected=rejected)


def _get_image_or_404(db: Session, image_id: str) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise ImageNotFoundError(f"Image {image_id} does not exist.", details={"image_id": image_id})
    return image


@router.get("/images/{image_id}/thumbnail")
def get_thumbnail(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = _get_image_or_404(db, image_id)
    path = storage.get_thumbnail_path(image.thumbnail_path)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/images/{image_id}/original")
def get_original(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = _get_image_or_404(db, image_id)
    path = storage.get_image_path(image.stored_path)
    return FileResponse(path, media_type=image.content_type)


@router.get("/images/{image_id}/annotated", response_model=None)
def get_annotated(image_id: str, db: Session = Depends(get_db)) -> NoReturn:
    from fastapi import HTTPException

    _get_image_or_404(db, image_id)
    raise HTTPException(status_code=404, detail="Annotated image view is not implemented (optional, docs/api.md).")
