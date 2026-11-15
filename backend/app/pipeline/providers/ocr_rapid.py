"""RapidOCR provider (default; see docs/dataset-notes.md section 5 for why)."""
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from app.pipeline.types import OcrLine, OcrSource

_engine: RapidOCR | None = None


def _get_engine() -> RapidOCR:
    global _engine
    if _engine is None:
        # Parallelism comes from the ProcessPoolExecutor in cli.py (one process per
        # worker), not from onnxruntime's own thread pool. The library's default
        # (-1 = use all cores) means N worker processes each spawn a full-core-count
        # thread pool, oversubscribing the CPU N-fold; a 262-image run measured
        # mean OCR time blowing up from ~1.5s (single process) to ~26s (8 workers,
        # default threading). Pinning to 1 thread per session fixes that.
        _engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
    return _engine


def run_ocr(image_bgr: np.ndarray, source: OcrSource) -> list[OcrLine]:
    result, _ = _get_engine()(image_bgr)
    if not result:
        return []
    lines = []
    for box, text, conf in result:
        bbox = [(float(p[0]), float(p[1])) for p in box]
        lines.append(OcrLine(text=text, confidence=float(conf), bbox=bbox, source=source))
    return lines
