"""Stage 1: load and validate an image file."""
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import MIN_IMAGE_SIDE, WORKING_MAX_SIDE

Image.MAX_IMAGE_PIXELS = 200_000_000  # guard against decompression bombs


@dataclass
class LoadedImage:
    original_rgb: np.ndarray
    working_bgr: np.ndarray
    width: int
    height: int
    format: str | None
    has_exif: bool
    rotated: bool


class ImageLoadError(Exception):
    pass


class ImageTooSmallError(Exception):
    pass


def load_and_validate(path: str) -> LoadedImage:
    """Open, verify, EXIF-correct, and produce a downscaled working copy.

    Raises ImageLoadError for corrupt/unreadable files and ImageTooSmallError
    for images below the minimum side length. Callers turn these into
    IMAGE_CORRUPT / rejection outcomes; this function never returns a partial result.
    """
    try:
        with Image.open(path) as im:
            im.load()  # force full decode now, not lazily later
            fmt = im.format
            has_exif = bool(im.getexif())
            size_before = im.size
            im = ImageOps.exif_transpose(im)
            rotated = has_exif and im.size != size_before
            im = im.convert("RGB")
            width, height = im.size
            if min(width, height) < MIN_IMAGE_SIDE:
                raise ImageTooSmallError(f"shorter side {min(width, height)}px < {MIN_IMAGE_SIDE}px")

            original_rgb = np.array(im)
            working_im = im
            if max(width, height) > WORKING_MAX_SIDE:
                scale = WORKING_MAX_SIDE / max(width, height)
                working_im = im.resize(
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    Image.BILINEAR,
                )
            working_rgb = np.array(working_im)
    except ImageTooSmallError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImageLoadError(str(e)) from e

    working_bgr = working_rgb[:, :, ::-1].copy()
    return LoadedImage(
        original_rgb=original_rgb,
        working_bgr=working_bgr,
        width=width,
        height=height,
        format=fmt,
        has_exif=has_exif,
        rotated=rotated,
    )
