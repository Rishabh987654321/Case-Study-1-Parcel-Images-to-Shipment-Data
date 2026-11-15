"""Stage: OCR orchestration. Provider-agnostic; default provider is RapidOCR."""
import time
from typing import Protocol

import cv2
import numpy as np

from app.pipeline.types import OcrLine

_MIN_LINES_BEFORE_ROTATE_RETRY = 3


class OcrProvider(Protocol):
    def __call__(self, image_bgr: np.ndarray, source: str) -> list[OcrLine]: ...


def _default_provider() -> OcrProvider:
    from app.pipeline.providers.ocr_rapid import run_ocr

    return run_ocr


def run(
    working_bgr: np.ndarray,
    label_crop: np.ndarray | None,
    provider: OcrProvider | None = None,
) -> tuple[list[OcrLine], float]:
    ocr = provider or _default_provider()
    t_start = time.perf_counter()
    lines = list(ocr(working_bgr, "full"))

    if label_crop is not None:
        lines.extend(ocr(label_crop, "crop"))

    if len(lines) < _MIN_LINES_BEFORE_ROTATE_RETRY:
        base = label_crop if label_crop is not None else working_bgr
        source = "crop" if label_crop is not None else "full"
        for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180):
            rotated = cv2.rotate(base, rot)
            extra = ocr(rotated, source)
            lines.extend(extra)
            if len(lines) >= _MIN_LINES_BEFORE_ROTATE_RETRY:
                break

    return lines, time.perf_counter() - t_start
