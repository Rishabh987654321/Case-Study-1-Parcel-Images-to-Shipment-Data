"""Stage 2: image quality metrics. Used for flags/confidence, never to alter pixels."""
import cv2
import numpy as np

from app.pipeline.types import QualityMetrics


def compute_quality(working_bgr: np.ndarray, original_width: int, original_height: int) -> QualityMetrics:
    gray = cv2.cvtColor(working_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    return QualityMetrics(
        blur_score=blur_score,
        brightness=brightness,
        contrast=contrast,
        width=original_width,
        height=original_height,
    )
