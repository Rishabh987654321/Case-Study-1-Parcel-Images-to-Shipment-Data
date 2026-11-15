"""Stage: locate the parcel/label region so barcode decode and OCR can retry on a
cropped, upscaled version of it. Phase 0 found only 2/20 images decode a barcode
on the full downscaled frame; most labels are a small region in a wide sorter shot.

This is a cheap heuristic (brightness + contour), not a scene classifier: it is
allowed to pick the wrong bright blob (e.g. an empty conveyor) on edge cases,
because a crop that doesn't contain a label simply fails to decode anything on
retry and the pipeline falls back to the full-image result. Decisions like
NO_PARCEL do not depend on this stage being precise.
"""
import cv2
import numpy as np

from app.config import (
    LABEL_CROP_PADDING_PCT,
    LABEL_MAX_UPSCALE,
    LABEL_MIN_AREA_PCT,
    LABEL_UPSCALE_MIN_SIDE,
)
from app.pipeline.types import LabelRegionInfo

_FILL_MIN = 0.35
_ASPECT_RANGE = (0.25, 4.0)
_NEAR_ORIGIN_PCT = 0.03
_CLOSE_KERNEL = 25


def _find_candidate_bboxes(gray: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    """All bright rectangular blobs passing the label-shape filters, largest
    first - not just the best one. `cv2.findContours(..., RETR_EXTERNAL, ...)`
    already returns disjoint external contours, so two entries here are by
    construction two separate connected bright regions (used by scene.py as a
    multiple-parcels signal when 2+ survive)."""
    h, w = gray.shape
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (_CLOSE_KERNEL, _CLOSE_KERNEL))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_area = w * h
    candidates: list[tuple[int, int, int, int, float]] = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        bbox_area = cw * ch
        if bbox_area < LABEL_MIN_AREA_PCT * image_area:
            continue
        aspect = cw / ch if ch else 0
        if not (_ASPECT_RANGE[0] <= aspect <= _ASPECT_RANGE[1]):
            continue
        fill = cv2.contourArea(c) / bbox_area if bbox_area else 0
        if fill < _FILL_MIN:
            continue
        if x < _NEAR_ORIGIN_PCT * w and y < _NEAR_ORIGIN_PCT * h:
            continue  # likely the sorter overlay text block, not a parcel/label
        candidates.append((x, y, cw, ch, fill))
    candidates.sort(key=lambda c: c[2] * c[3], reverse=True)
    return candidates


def _find_candidate_bbox(gray: np.ndarray) -> tuple[int, int, int, int, float] | None:
    candidates = _find_candidate_bboxes(gray)
    return candidates[0] if candidates else None


def find_label_region_candidates(working_bgr: np.ndarray) -> list[LabelRegionInfo]:
    """All qualifying label-shaped regions (not just the one `detect_label_region`
    crops for barcode/OCR retry) - used by scene.py's multiple-parcels signal
    (Phase 5): 2+ separated, large-enough bright regions is independent evidence
    of 2+ parcels even when no barcode decoded on either one."""
    gray = cv2.cvtColor(working_bgr, cv2.COLOR_BGR2GRAY)
    return [LabelRegionInfo(bbox_xywh=(x, y, cw, ch), confidence=fill, upscale_factor=1.0) for x, y, cw, ch, fill in _find_candidate_bboxes(gray)]


def detect_label_region(working_bgr: np.ndarray) -> tuple[np.ndarray, LabelRegionInfo] | None:
    """Return (cropped_upscaled_bgr, info) for the best label/parcel candidate, or None."""
    gray = cv2.cvtColor(working_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    found = _find_candidate_bbox(gray)
    if found is None:
        return None
    x, y, cw, ch, fill = found

    pad_x = int(cw * LABEL_CROP_PADDING_PCT)
    pad_y = int(ch * LABEL_CROP_PADDING_PCT)
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(w, x + cw + pad_x)
    y1 = min(h, y + ch + pad_y)
    crop = working_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return None

    short_side = min(crop.shape[0], crop.shape[1])
    upscale = 1.0
    if short_side < LABEL_UPSCALE_MIN_SIDE and short_side > 0:
        upscale = min(LABEL_MAX_UPSCALE, LABEL_UPSCALE_MIN_SIDE / short_side)
    if upscale > 1.0:
        crop = cv2.resize(crop, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

    info = LabelRegionInfo(bbox_xywh=(x0, y0, x1 - x0, y1 - y0), confidence=fill, upscale_factor=upscale)
    return crop, info
