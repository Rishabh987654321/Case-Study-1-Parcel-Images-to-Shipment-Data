"""Stage: deterministic scene signals (heuristic provider only).

A pluggable provider interface is left for an optional model (ollama/clip);
SCENE_PROVIDER is read but anything other than "heuristic" currently falls back
to it with a SCENE_PROVIDER_UNAVAILABLE warning (see docs/architecture.md
section 7) - no model is wired up today.

Phase 5 strengthened four signals without adding a model dependency, directly
targeting the two known wrong cases from the Phase 1 evaluation (see
eval/reports/report_20261113.md and docs/flag_taxonomy.md section 2):

1. `parcel_present` no longer treats a found label *region* (by itself) as
   evidence of a parcel - only an actual decoded barcode or actual non-overlay
   text does. This matches label_detect.py's own documented contract ("this is
   a cheap heuristic... allowed to pick the wrong blob... decisions like
   NO_PARCEL do not depend on this stage being precise") which the pre-Phase-5
   formula violated: a bare bright platform surface could get misidentified as
   a label region and that alone was enough to mark a parcel "present," which
   let a stale overlay AWB through as a false OK ("No Shipment ccaptured...").
2. `distinct_label_regions` - 2+ separate, large-enough bright/structured
   regions is independent evidence of 2+ parcels even when no barcode decodes
   on either one (the "Multiple shipment packets..." case: two real parcels,
   zero decoded barcodes, so the old barcode-count-only check never fired).
3. `distinct_ocr_awb_regions` - same idea via OCR: 2+ differently-valued,
   spatially-separated AWB-shaped numeric tokens in the label text.
4. `label_region_clipped_by_border` - the detected label bbox itself touching
   the frame edge is now an explicit PARTIAL_PARCEL signal, not just a
   touching barcode or truncated text line.
5. `label_region_low_confidence_text` - a lighter, data-only proxy for
   "irregular occlusion" (Task 1D asked for dark-patch pixel analysis; that
   needs the actual crop pixels at this stage and wasn't validated against any
   real case in the time available, so a defensible proxy was used instead,
   per Phase 5's own report instructions - see the Phase 5 report for why):
   when a label region has *some* OCR text but at low confidence, that reads
   as a partially-covered label (blocked), as opposed to zero text (unreadable
   / quality-poor), which the existing fallback flags already handle.
"""
import math
import re

from app.config import BORDER_MARGIN_PCT, SCENE_PROVIDER
from app.pipeline.courier_patterns import match_courier
from app.pipeline.overlay import non_overlay_lines
from app.pipeline.types import (
    BarcodeResult,
    LabelRegionInfo,
    OcrLine,
    OverlayData,
    SceneSignals,
)

# Mirrors parse_fields.py's _BARE_NUMERIC_PATTERN; kept local rather than
# imported since that name is a private implementation detail of parse_fields.
_BARE_NUMERIC_RE = re.compile(r"\b([0-9]{8,16})\b")
_MIN_SEPARATION_FRAC = 0.15  # fraction of the image diagonal two AWB tokens must clear to count as separate parcels
_LOW_TEXT_CONF_THRESHOLD = 0.5  # below this, OCR text within a label region reads as "there, but struggling" (likely occluded)


def _line_center(line: OcrLine) -> tuple[float, float]:
    xs = [p[0] for p in line.bbox]
    ys = [p[1] for p in line.bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)


def _distinct_awb_text_regions(lines: list[OcrLine], image_width: int, image_height: int) -> int:
    # Specific-courier-pattern match only (match_courier), not the generic 8-20
    # alphanumeric fallback is_awb_shaped() also accepts - a label routinely
    # carries a second, non-AWB number (pickup/order code) that still satisfies
    # the generic shape; decide.py's _distinct_awb_barcodes already solved this
    # exact problem for barcodes the same way (see its docstring) - mirrored here
    # after the generic check produced a false MULTIPLE_PARCELS on a clean single-
    # parcel image (ms7_jpeg: real AWB 77549916382 plus an unrelated 6-digit code).
    found: list[tuple[str, tuple[float, float]]] = []
    seen_values: set[str] = set()
    for line in lines:
        if not line.bbox:
            continue
        for m in _BARE_NUMERIC_RE.finditer(line.text):
            value = m.group(1)
            if value in seen_values or match_courier(value) is None:
                continue
            seen_values.add(value)
            found.append((value, _line_center(line)))

    if len(found) < 2:
        return len(found)

    diagonal = math.hypot(image_width, image_height)
    min_dist = diagonal * _MIN_SEPARATION_FRAC
    cluster_centers: list[tuple[float, float]] = []
    for _, center in found:
        if all(math.hypot(center[0] - c[0], center[1] - c[1]) >= min_dist for c in cluster_centers):
            cluster_centers.append(center)
    return len(cluster_centers)


def _label_region_clipped(label_region: LabelRegionInfo | None, image_width: int, image_height: int) -> bool:
    if label_region is None:
        return False
    x, y, w, h = label_region.bbox_xywh
    margin_x = image_width * BORDER_MARGIN_PCT
    margin_y = image_height * BORDER_MARGIN_PCT
    return x <= margin_x or y <= margin_y or (x + w) >= image_width - margin_x or (y + h) >= image_height - margin_y


def _label_region_mean_text_confidence(label_region: LabelRegionInfo | None, ocr_lines: list[OcrLine]) -> float | None:
    if label_region is None:
        return None
    x, y, w, h = label_region.bbox_xywh
    pad_x, pad_y = w * 0.1, h * 0.1
    x0, y0, x1, y1 = x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y
    confidences = []
    for line in ocr_lines:
        if not line.bbox:
            continue
        cx, cy = _line_center(line)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            confidences.append(line.confidence)
    return (sum(confidences) / len(confidences)) if confidences else None


def compute_scene_signals(
    barcodes: list[BarcodeResult],
    ocr_lines: list[OcrLine],
    overlay: OverlayData,
    label_region: LabelRegionInfo | None,
    label_region_candidates: list[LabelRegionInfo],
    image_width: int,
    image_height: int,
) -> tuple[SceneSignals, list[str]]:
    warnings: list[str] = []
    if SCENE_PROVIDER != "heuristic":
        warnings.append("SCENE_PROVIDER_UNAVAILABLE")

    barcode_touches_border = any(b.touches_border for b in barcodes)

    # Evidence of a parcel independent of the overlay: OCR lines the overlay
    # vocabulary doesn't explain (see overlay.non_overlay_lines), not just "any text",
    # since the overlay's own Location/Time/Sorter_ID lines are not evidence of a parcel.
    # The sorter overlay is almost always positioned in a corner by design, so its own
    # text routinely touches the frame edge - that is not evidence the physical parcel
    # is cut off, so border-truncation is judged on this same non-overlay line set.
    checked_lines = non_overlay_lines(ocr_lines) if overlay.detected else ocr_lines
    has_independent_text = len(checked_lines) > 0

    margin_x = image_width * BORDER_MARGIN_PCT
    margin_y = image_height * BORDER_MARGIN_PCT
    text_truncated = False
    for line in checked_lines:
        if not line.bbox:
            continue
        xs = [p[0] for p in line.bbox]
        ys = [p[1] for p in line.bbox]
        if min(xs) <= margin_x or max(xs) >= image_width - margin_x or min(ys) <= margin_y or max(ys) >= image_height - margin_y:
            text_truncated = True
            break

    distinct_awb_values = {b.value for b in barcodes}
    distinct_count = len(distinct_awb_values)

    label_region_found = label_region is not None
    barcode_region_found_but_not_decoded = label_region_found and not barcodes

    # Phase 5: a label *region* alone (label_detect.py is "allowed to pick the
    # wrong blob" per its own docstring) is not parcel evidence by itself -
    # only an actual decoded barcode or actual independent text is. Fixes the
    # "No Shipment ccaptured..." false-OK (bright platform misread as a label
    # region, which used to be enough on its own to trust the stale overlay).
    parcel_present = bool(barcodes) or has_independent_text

    distinct_label_regions = len(label_region_candidates)
    distinct_ocr_awb_regions = _distinct_awb_text_regions(checked_lines, image_width, image_height)
    label_region_clipped_by_border = _label_region_clipped(label_region, image_width, image_height)

    mean_text_conf = _label_region_mean_text_confidence(label_region, ocr_lines)
    label_region_low_confidence_text = (
        label_region_found and not barcodes and mean_text_conf is not None and mean_text_conf < _LOW_TEXT_CONF_THRESHOLD
    )

    signals = SceneSignals(
        barcode_touches_border=barcode_touches_border,
        text_truncated_at_border=text_truncated,
        distinct_awb_barcode_count=distinct_count,
        label_region_found=label_region_found,
        barcode_region_found_but_not_decoded=barcode_region_found_but_not_decoded,
        parcel_present=parcel_present,
        distinct_label_regions=distinct_label_regions,
        distinct_ocr_awb_regions=distinct_ocr_awb_regions,
        label_region_clipped_by_border=label_region_clipped_by_border,
        label_region_low_confidence_text=label_region_low_confidence_text,
    )
    return signals, warnings
