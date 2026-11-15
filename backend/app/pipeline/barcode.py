"""Stage: barcode detection with a retry cascade, now including a label-crop retry
(Phase 0 found only 2/20 images decode on the full frame; see dataset-notes.md)."""
import time

import cv2
import numpy as np
import zxingcpp

from app.config import BORDER_MARGIN_PCT
from app.pipeline.types import BarcodeResult, Point

Rect = tuple[int, int, int, int]  # x0, y0, w, h in working-image coordinates


def _polygon_from_barcode(barcode, offset: tuple[int, int] = (0, 0), scale: float = 1.0) -> list[Point]:
    pos = barcode.position
    pts = [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]
    return [((p.x / scale) + offset[0], (p.y / scale) + offset[1]) for p in pts]


def _touches_border(polygon: list[Point], image_w: int, image_h: int) -> bool:
    margin_x = image_w * BORDER_MARGIN_PCT
    margin_y = image_h * BORDER_MARGIN_PCT
    for x, y in polygon:
        if x <= margin_x or x >= image_w - margin_x or y <= margin_y or y >= image_h - margin_y:
            return True
    return False


def _decode(image: np.ndarray) -> list:
    try:
        return zxingcpp.read_barcodes(image)
    except Exception:  # noqa: BLE001 - never let a decode crash the pipeline
        return []


def decode_barcodes(
    working_bgr: np.ndarray,
    label_crop: np.ndarray | None,
    label_offset: tuple[int, int],
    label_scale: float,
) -> tuple[list[BarcodeResult], float]:
    """Retry cascade: full image -> label crop -> crop+CLAHE -> crop+threshold -> crop rotations.

    bbox polygons are always reported in working_bgr coordinates (crop results are
    mapped back via label_offset/label_scale) so border-touch checks are consistent.
    """
    t_start = time.perf_counter()
    h, w = working_bgr.shape[:2]
    results: list[BarcodeResult] = []

    def record(raw_barcodes: list, source: str, offset: tuple[int, int] = (0, 0), scale: float = 1.0) -> None:
        for b in raw_barcodes:
            polygon = _polygon_from_barcode(b, offset, scale)
            results.append(
                BarcodeResult(
                    value=b.text,
                    symbology=str(b.format),
                    bbox_polygon=polygon,
                    touches_border=_touches_border(polygon, w, h),
                    source_image=source,
                )
            )

    found = _decode(working_bgr)
    record(found, "original")
    if results:
        return results, time.perf_counter() - t_start

    if label_crop is not None:
        found = _decode(label_crop)
        record(found, "crop", label_offset, label_scale)
        if results:
            return results, time.perf_counter() - t_start

        gray = cv2.cvtColor(label_crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        found = _decode(enhanced)
        record(found, "enhanced", label_offset, label_scale)
        if results:
            return results, time.perf_counter() - t_start

        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 10)
        found = _decode(thresh)
        record(found, "enhanced", label_offset, label_scale)
        if results:
            return results, time.perf_counter() - t_start

        for angle, rot in ((90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180), (270, cv2.ROTATE_90_COUNTERCLOCKWISE)):
            rotated = cv2.rotate(label_crop, rot)
            found = _decode(rotated)
            if found:
                # Rotated crop coordinates no longer map cleanly back; record without
                # a precise polygon rather than report a wrong border-touch verdict.
                for b in found:
                    results.append(
                        BarcodeResult(
                            value=b.text,
                            symbology=str(b.format),
                            bbox_polygon=[],
                            touches_border=False,
                            source_image="enhanced",
                        )
                    )
                return results, time.perf_counter() - t_start

    return results, time.perf_counter() - t_start
