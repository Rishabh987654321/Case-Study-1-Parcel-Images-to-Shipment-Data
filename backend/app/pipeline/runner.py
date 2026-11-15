"""Orchestrates every stage for one image. Never raises - on any unexpected
exception it returns an ERROR/PROCESSING_ERROR ResultRecord instead of crashing
the caller (CLI or, later, a worker process)."""
import logging
import time
import uuid
from datetime import UTC, datetime

from app.config import PIPELINE_VERSION
from app.pipeline import (
    barcode,
    label_detect,
    ocr,
    overlay,
    parse_fields,
    quality,
    scene,
)
from app.pipeline.decide import decide
from app.pipeline.preprocess import (
    ImageLoadError,
    ImageTooSmallError,
    load_and_validate,
)
from app.pipeline.types import PipelineEvidence, QualityMetrics, ResultRecord

logger = logging.getLogger("app.pipeline")


def process_image(image_path: str, filename: str, image_id: str | None = None) -> ResultRecord:
    image_id = image_id or str(uuid.uuid4())
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    try:
        return _process_image_inner(image_path, filename, image_id, timings, t0)
    except (ImageLoadError, ImageTooSmallError) as e:
        return build_error_record(image_id, filename, "IMAGE_CORRUPT", str(e), t0)
    except Exception:  # a bug in one image must not stop the batch
        # docs/architecture.md section 9: stack traces go to logs, not responses -
        # the full traceback is logged here (with the image_id needed to find the
        # row again) but never stored in the record a user can see via the API/CSV.
        logger.exception("Pipeline processing failed for image_id=%s", image_id)
        return build_error_record(image_id, filename, "PROCESSING_ERROR", "An unexpected error occurred while processing this image.", t0)


def _process_image_inner(
    image_path: str, filename: str, image_id: str, timings: dict[str, float], t0: float
) -> ResultRecord:
    t = time.perf_counter()
    loaded = load_and_validate(image_path)
    timings["preprocess"] = time.perf_counter() - t

    t = time.perf_counter()
    q = quality.compute_quality(loaded.working_bgr, loaded.width, loaded.height)
    timings["quality"] = time.perf_counter() - t

    t = time.perf_counter()
    label = label_detect.detect_label_region(loaded.working_bgr)
    label_crop, label_info = (label[0], label[1]) if label else (None, None)
    label_offset = (label_info.bbox_xywh[0], label_info.bbox_xywh[1]) if label_info else (0, 0)
    label_scale = label_info.upscale_factor if label_info else 1.0
    label_region_candidates = label_detect.find_label_region_candidates(loaded.working_bgr)
    timings["label_detect"] = time.perf_counter() - t

    t = time.perf_counter()
    barcodes, barcode_time = barcode.decode_barcodes(loaded.working_bgr, label_crop, label_offset, label_scale)
    timings["barcode"] = barcode_time

    t = time.perf_counter()
    ocr_lines, ocr_time = ocr.run(loaded.working_bgr, label_crop)
    timings["ocr"] = ocr_time

    t = time.perf_counter()
    overlay_data = overlay.parse_overlay(ocr_lines)
    timings["overlay"] = time.perf_counter() - t

    t = time.perf_counter()
    awb_candidates = parse_fields.find_awb_candidates(ocr_lines)
    label_fields = parse_fields.parse_weight_and_dimensions(ocr_lines)
    timings["parse_fields"] = time.perf_counter() - t

    t = time.perf_counter()
    scene_signals, scene_warnings = scene.compute_scene_signals(
        barcodes, ocr_lines, overlay_data, label_info, label_region_candidates, loaded.width, loaded.height
    )
    timings["scene"] = time.perf_counter() - t

    t = time.perf_counter()
    decision = decide(
        load_error=None,
        quality=q,
        barcodes=barcodes,
        ocr_line_count=len(ocr_lines),
        overlay=overlay_data,
        ocr_awb_candidates=awb_candidates,
        label_fields=label_fields,
        scene=scene_signals,
    )
    timings["decide"] = time.perf_counter() - t

    warnings = list(dict.fromkeys(decision.warnings + scene_warnings))
    if loaded.rotated:
        warnings.append("ROTATED_IMAGE_FIXED")

    evidence = PipelineEvidence(
        quality=q,
        barcodes=barcodes,
        ocr_lines=ocr_lines,
        overlay=overlay_data,
        label_region=label_info,
        awb_candidates=awb_candidates,
        parsed_fields=label_fields,
        scene_signals=scene_signals,
        timings=timings,
    )

    return ResultRecord(
        image_id=image_id,
        filename=filename,
        status=decision.status,
        primary_flag=decision.primary_flag,
        flag_reason=decision.flag_reason,
        warnings=warnings,
        awb=decision.awb,
        awb_suggestion=decision.awb_suggestion,
        awb_source=decision.awb_source,
        awb_confidence=decision.awb_confidence,
        weight_kg=decision.weight_kg,
        weight_raw=decision.weight_raw,
        length_cm=decision.length_cm,
        width_cm=decision.width_cm,
        height_cm=decision.height_cm,
        dimensions_raw=decision.dimensions_raw,
        courier=decision.courier,
        confidence=decision.confidence,
        evidence=evidence,
        pipeline_version=PIPELINE_VERSION,
        processing_ms=int((time.perf_counter() - t0) * 1000),
        processed_at=datetime.now(UTC).isoformat(),
    )


def build_error_record(image_id: str, filename: str, flag: str, reason: str, t0: float) -> ResultRecord:
    return ResultRecord(
        image_id=image_id,
        filename=filename,
        status="ERROR",
        primary_flag=flag,
        flag_reason=reason.splitlines()[-1] if reason else flag,
        warnings=[],
        awb=None,
        awb_suggestion=None,
        awb_source=None,
        awb_confidence=0.0,
        weight_kg=None,
        weight_raw=None,
        length_cm=None,
        width_cm=None,
        height_cm=None,
        dimensions_raw=None,
        courier=None,
        confidence=0.0,
        evidence=PipelineEvidence(quality=QualityMetrics(0, 0, 0, 0, 0), load_error=reason),
        pipeline_version=PIPELINE_VERSION,
        processing_ms=int((time.perf_counter() - t0) * 1000),
        processed_at=datetime.now(UTC).isoformat(),
    )
