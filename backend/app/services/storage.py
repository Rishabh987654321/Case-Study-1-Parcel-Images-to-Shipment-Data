"""File-handling service: validates uploads by content, saves originals and
thumbnails under generated ids (never the client filename), computes sha256 for
duplicate detection. No DB access here - batch/duplicate bookkeeping lives in
the API layer so this module stays a plain, testable file-ops module.
"""
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from app.config import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_MB,
    MAX_IMAGE_PIXELS,
    MIN_IMAGE_SIDE,
    THUMBNAIL_DIR,
    THUMBNAIL_MAX_SIDE,
    UPLOAD_DIR,
)

PILImage.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_FORMAT_TO_CONTENT_TYPE = {"JPEG": "image/jpeg", "PNG": "image/png"}
_FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png"}


class UploadRejection(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class SavedImage:
    image_id: str
    stored_path: str  # relative to UPLOAD_DIR
    thumbnail_path: str  # relative to THUMBNAIL_DIR
    file_size: int
    content_type: str
    sha256: str
    width: int
    height: int


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate(data: bytes) -> tuple[str, int, int]:
    """Returns (pillow_format, width, height) or raises UploadRejection (code only -
    the API layer renders the per-file, filename-including message; see docs/design.md
    section 6 for the exact wording)."""
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise UploadRejection("FILE_TOO_LARGE", "file too large")

    import io

    try:
        with PILImage.open(io.BytesIO(data)) as im:
            im.verify()
    except PILImage.DecompressionBombError as e:
        raise UploadRejection("IMAGE_TOO_LARGE", "decompression bomb guard") from e
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise UploadRejection("NOT_AN_IMAGE", "not an image") from e

    # verify() leaves the file object unusable for further reads; reopen to inspect it
    try:
        with PILImage.open(io.BytesIO(data)) as im:
            im.load()
            fmt, width, height = im.format, im.width, im.height
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise UploadRejection("CORRUPT_IMAGE", "corrupt image") from e

    # Phase 6: PILImage.MAX_IMAGE_PIXELS only makes Pillow itself raise
    # DecompressionBombError above *2x* that limit - anywhere between 1x and 2x
    # it just emits a warning and loads the image anyway (confirmed: a
    # 169-megapixel image loaded fine against this app's 144-megapixel limit).
    # Enforce the limit explicitly rather than relying on Pillow's own fuzz factor.
    if width * height > MAX_IMAGE_PIXELS:
        raise UploadRejection("IMAGE_TOO_LARGE", "decompression bomb guard")

    content_type = _FORMAT_TO_CONTENT_TYPE.get(fmt or "")
    if content_type is None or content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadRejection("UNSUPPORTED_TYPE", "unsupported type")

    if min(width, height) < MIN_IMAGE_SIDE:
        raise UploadRejection("IMAGE_TOO_SMALL", "image too small")

    return fmt, width, height


def save_upload(data: bytes) -> SavedImage:
    """Validate by content and persist original + thumbnail under a generated id.
    Raises UploadRejection (never writes files) if validation fails."""
    fmt, width, height = _validate(data)
    content_type = _FORMAT_TO_CONTENT_TYPE[fmt]
    ext = _FORMAT_TO_EXT[fmt]
    sha256 = compute_sha256(data)
    image_id = uuid.uuid4().hex

    upload_dir = Path(UPLOAD_DIR)
    thumb_dir = Path(THUMBNAIL_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    stored_rel = f"{image_id}{ext}"
    stored_abs = upload_dir / stored_rel
    stored_abs.write_bytes(data)

    thumb_rel = f"{image_id}.jpg"
    thumb_abs = thumb_dir / thumb_rel
    import io

    with PILImage.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
        im.save(thumb_abs, format="JPEG", quality=85)

    return SavedImage(
        image_id=image_id,
        stored_path=stored_rel,
        thumbnail_path=thumb_rel,
        file_size=len(data),
        content_type=content_type,
        sha256=sha256,
        width=width,
        height=height,
    )


def copy_as_duplicate(existing: SavedImage) -> SavedImage:
    """Register a new image id pointing at an already-saved duplicate's files
    (same sha256 within the batch) instead of writing the bytes again."""
    return SavedImage(
        image_id=uuid.uuid4().hex,
        stored_path=existing.stored_path,
        thumbnail_path=existing.thumbnail_path,
        file_size=existing.file_size,
        content_type=existing.content_type,
        sha256=existing.sha256,
        width=existing.width,
        height=existing.height,
    )


def get_image_path(stored_path: str) -> Path:
    return Path(UPLOAD_DIR) / stored_path


def get_thumbnail_path(thumbnail_path: str) -> Path:
    return Path(THUMBNAIL_DIR) / thumbnail_path


def delete_files(stored_paths: list[str], thumbnail_paths: list[str]) -> None:
    for rel in set(stored_paths):
        path = get_image_path(rel)
        path.unlink(missing_ok=True)
    for rel in set(thumbnail_paths):
        path = get_thumbnail_path(rel)
        path.unlink(missing_ok=True)
