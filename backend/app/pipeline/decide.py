"""The only module that turns evidence into a verdict (docs/flag_taxonomy.md).

Three independent AWB channels are cross-validated: barcode, printed-label OCR,
and the sorter-camera text overlay (docs/dataset-notes.md section 2). Agreement
between channels raises confidence; disagreement is CONFLICTING_READS, never a
guess. See docs/flag_taxonomy.md section 4 and the AWB_CROSS_VALIDATION table in
there for the confidence numbers this module implements.
"""
from dataclasses import dataclass, field

from app.config import BLUR_MIN, BRIGHTNESS_MAX, BRIGHTNESS_MIN
from app.pipeline.courier_patterns import is_awb_shaped, match_courier
from app.pipeline.types import (
    AwbCandidate,
    BarcodeResult,
    OverlayData,
    ParsedFields,
    QualityMetrics,
    SceneSignals,
)


@dataclass
class Decision:
    status: str
    primary_flag: str | None
    flag_reason: str | None
    warnings: list[str] = field(default_factory=list)
    awb: str | None = None
    awb_suggestion: str | None = None
    awb_source: str | None = None
    awb_confidence: float = 0.0
    weight_kg: float | None = None
    weight_raw: str | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    dimensions_raw: str | None = None
    courier: str | None = None
    confidence: float = 0.0


def _distinct_awb_barcodes(barcodes: list[BarcodeResult]) -> list[str]:
    """Barcode values shaped like a SPECIFIC courier's AWB (not just the generic
    8-20 alphanumeric fallback). Many labels carry a second, non-AWB barcode
    (pickup/return code, order id - e.g. Delhivery's "DLVPCE..." codes) that is
    still generic-shaped; counting those here would create false multi-parcel
    or false-conflict signals against a correct overlay/AWB reading."""
    seen = {}
    for b in barcodes:
        if match_courier(b.value) is not None:
            seen[b.value] = True
    return list(seen.keys())


def _resolve_awb(
    barcode_values: list[str],
    overlay: OverlayData,
    ocr_candidates: list[AwbCandidate],
    parcel_present: bool,
    generic_barcode_values: list[str] | None = None,
) -> dict:
    """Returns a dict with keys: outcome ('ok'|'conflicting'|'low_confidence'|'none'),
    awb, source, confidence, suggestion, courier, reason.

    barcode_values must already be filtered to specific-courier matches (see
    _distinct_awb_barcodes) so a non-AWB barcode (pickup/return code, order id)
    never gets treated as competing evidence against the overlay or OCR.
    generic_barcode_values is a last-resort fallback: used only when nothing
    else (specific barcode, overlay, OCR) has anything to offer, matching
    flag_taxonomy.md's "barcode matches a known/generic AWB pattern" OK rule.
    """
    barcode_awb = barcode_values[0] if len(barcode_values) == 1 else None
    overlay_awb = overlay.awb if (overlay.detected and overlay.awb and is_awb_shaped(overlay.awb)) else None
    ocr_match = next((c for c in ocr_candidates if c.validated_by_pattern), None)
    generic_barcode_awb = (
        generic_barcode_values[0] if generic_barcode_values and len(generic_barcode_values) == 1 else None
    )

    def courier_of(value: str) -> str | None:
        m = match_courier(value)
        return m.name if m else None

    if barcode_awb and overlay_awb:
        if barcode_awb == overlay_awb:
            return {
                "outcome": "ok", "awb": barcode_awb, "source": "barcode+overlay",
                "confidence": 0.98, "courier": courier_of(barcode_awb),
                "reason": f"Barcode decoded {barcode_awb}, confirmed by the sorter overlay text.",
            }
        return {
            "outcome": "conflicting", "suggestion": f"{barcode_awb} / {overlay_awb}",
            "reason": f"Barcode reads {barcode_awb} but the sorter overlay reports {overlay_awb}; they disagree.",
        }

    if barcode_awb and ocr_match and ocr_match.value != barcode_awb:
        return {
            "outcome": "conflicting", "suggestion": f"{barcode_awb} / {ocr_match.value}",
            "reason": f"Barcode reads {barcode_awb} but label text reads {ocr_match.value}; they disagree.",
        }

    if barcode_awb:
        if ocr_match and ocr_match.value == barcode_awb:
            return {
                "outcome": "ok", "awb": barcode_awb, "source": "both",
                "confidence": 0.95, "courier": courier_of(barcode_awb),
                "reason": f"Barcode decoded {barcode_awb}, confirmed by text on the label.",
            }
        return {
            "outcome": "ok", "awb": barcode_awb, "source": "barcode",
            "confidence": 0.80, "courier": courier_of(barcode_awb),
            "reason": f"Barcode decoded {barcode_awb}; no separate confirmation but it is the only barcode found.",
        }

    if overlay_awb:
        if not parcel_present:
            return {"outcome": "stale_overlay", "suggestion": overlay_awb,
                     "reason": f"Sorter overlay reports AWB {overlay_awb} but no parcel is visible in the frame."}
        if ocr_match and ocr_match.value == overlay_awb:
            return {
                "outcome": "ok", "awb": overlay_awb, "source": "ocr+overlay",
                "confidence": 0.95, "courier": courier_of(overlay_awb),
                "reason": f"Sorter overlay reports AWB {overlay_awb}, confirmed by text on the label.",
            }
        return {
            "outcome": "ok", "awb": overlay_awb, "source": "overlay",
            "confidence": 0.80, "courier": courier_of(overlay_awb),
            "reason": f"Sorter overlay reports AWB {overlay_awb}; no barcode decoded to confirm it.",
        }

    if ocr_match:
        return {
            "outcome": "low_confidence", "suggestion": ocr_match.value,
            "reason": f"Label text suggests AWB {ocr_match.value} but there is no barcode or overlay confirmation.",
        }

    if ocr_candidates:
        return {
            "outcome": "low_confidence", "suggestion": ocr_candidates[0].value,
            "reason": f"A number resembling an AWB ({ocr_candidates[0].value}) was read but did not validate against any known courier pattern.",
        }

    if generic_barcode_awb:
        return {
            "outcome": "ok", "awb": generic_barcode_awb, "source": "barcode",
            "confidence": 0.80, "courier": None,
            "reason": f"Barcode decoded {generic_barcode_awb}; no known courier pattern matched but it is the only barcode found.",
        }

    return {"outcome": "none", "reason": "No AWB evidence found from barcode, label text, or overlay."}


def decide(
    load_error: str | None,
    quality: QualityMetrics | None,
    barcodes: list[BarcodeResult],
    ocr_line_count: int,
    overlay: OverlayData,
    ocr_awb_candidates: list[AwbCandidate],
    label_fields: ParsedFields,
    scene: SceneSignals,
) -> Decision:
    if load_error is not None:
        return Decision(status="ERROR", primary_flag="IMAGE_CORRUPT", flag_reason=f"File could not be opened as an image: {load_error}")

    warnings = list(overlay.warnings) + list(label_fields.warnings)

    # merge weight/dimensions: prefer overlay (independently measured by the sorter), fall back to label OCR
    weight_kg = overlay.weight_kg if overlay.weight_kg is not None else label_fields.weight_kg
    weight_raw = overlay.weight_raw if overlay.weight_kg is not None else label_fields.weight_raw
    if overlay.length_cm is not None:
        length_cm, width_cm, height_cm, dims_raw = overlay.length_cm, overlay.width_cm, overlay.height_cm, overlay.dimensions_raw
    else:
        length_cm, width_cm, height_cm, dims_raw = (
            label_fields.length_cm, label_fields.width_cm, label_fields.height_cm, label_fields.dimensions_raw,
        )

    def with_fields(d: Decision) -> Decision:
        d.weight_kg, d.weight_raw = weight_kg, weight_raw
        d.length_cm, d.width_cm, d.height_cm, d.dimensions_raw = length_cm, width_cm, height_cm, dims_raw
        d.warnings = list(dict.fromkeys(warnings + d.warnings))
        return d

    awb_barcodes = _distinct_awb_barcodes(barcodes)
    generic_barcodes = list({b.value for b in barcodes if is_awb_shaped(b.value) and b.value not in awb_barcodes})

    if not scene.parcel_present:
        # Phase 5: give the specific "stale overlay" reason when there's a plausible
        # overlay AWB to name - this is the exact scenario a bare "frame appears
        # empty" reason would otherwise undersell (see "No Shipment ccaptured..." in
        # eval/reports/report_20261113.md: the overlay reports a real-looking AWB,
        # it's just not corroborated by anything else in a frame with no parcel).
        overlay_awb = overlay.awb if (overlay.detected and overlay.awb and is_awb_shaped(overlay.awb)) else None
        # Phase 6: re-running on the full 262-image dataset (not just the 38
        # ground-truth images) showed this fix costs real recall at scale - 69/262
        # images (26%) hit this branch, every one of them an overlay-only read with
        # zero independent corroboration, not a visibly-empty frame. A label_region
        # being found (even though label_detect.py is "allowed to pick the wrong
        # blob") is at least *something* solid-shaped in frame, which is weaker
        # evidence than independent text but stronger than nothing - route that
        # subset to LOW_CONFIDENCE_READ (suggestion only, never a confirmed awb)
        # rather than a flat "no parcel." 52/69 had no label_region at all either;
        # those stay NO_PARCEL since there is no ground truth here to justify a
        # further heuristic for that subset - see the Phase 5/6 report.
        if overlay_awb and scene.label_region_found:
            return with_fields(Decision(
                status="FLAGGED", primary_flag="LOW_CONFIDENCE_READ",
                flag_reason=f"Sorter overlay reports AWB {overlay_awb}; a label-like region was found but nothing independently confirms this reading.",
                awb_suggestion=overlay_awb,
            ))
        if overlay_awb:
            return with_fields(Decision(
                status="FLAGGED", primary_flag="NO_PARCEL",
                flag_reason=f"Sorter overlay reports AWB {overlay_awb} but no parcel is visible in the frame.",
                awb_suggestion=overlay_awb,
            ))
        return with_fields(Decision(
            status="FLAGGED", primary_flag="NO_PARCEL",
            flag_reason="No parcel, barcode, or label text found; the frame appears empty.",
        ))

    if len(awb_barcodes) >= 2:
        return with_fields(Decision(
            status="FLAGGED", primary_flag="MULTIPLE_PARCELS",
            flag_reason=f"{len(awb_barcodes)} different AWB-like barcodes were decoded in one frame.",
        ))

    # Phase 5: a second line of evidence for multiple parcels that doesn't
    # depend on a barcode ever decoding (the gap the check above misses -
    # see "Multiple shipment packets..." in eval/reports/report_20261113.md,
    # two real parcels, zero decoded barcodes). NOTE: an earlier version of this
    # check also used scene.distinct_label_regions >= 2 (2+ separate bright
    # label-shaped blobs). Tested against the full 38-image ground truth, it
    # produced a false MULTIPLE_PARCELS on a clean single-parcel image
    # (weight_image_19106721560684...: an unrelated bright surface elsewhere in
    # the frame also happened to pass the label-shape filters) and never once
    # correctly caught the actual target case - a bright-blob count alone isn't a
    # reliable enough multi-parcel signal. Removed from the decision; still
    # computed and kept in scene_signals as evidence for human review / a future
    # scene model, per "abstain over guess" (it's not safe to let this heuristic
    # abstain for other images when it was wrong this often in 38 images).
    if scene.distinct_ocr_awb_regions >= 2:
        return with_fields(Decision(
            status="FLAGGED", primary_flag="MULTIPLE_PARCELS",
            flag_reason=f"{scene.distinct_ocr_awb_regions} different AWB-like numbers were read in separate parts of the frame.",
        ))

    resolved = _resolve_awb(awb_barcodes, overlay, ocr_awb_candidates, scene.parcel_present, generic_barcodes)

    if resolved["outcome"] == "ok":
        return with_fields(Decision(
            status="OK", primary_flag=None, flag_reason=resolved["reason"],
            awb=resolved["awb"], awb_source=resolved["source"], awb_confidence=resolved["confidence"],
            courier=resolved["courier"], confidence=resolved["confidence"],
        ))

    if resolved["outcome"] == "stale_overlay":
        return with_fields(Decision(
            status="FLAGGED", primary_flag="NO_PARCEL", flag_reason=resolved["reason"],
            awb_suggestion=resolved["suggestion"],
        ))

    if scene.barcode_touches_border or scene.text_truncated_at_border or scene.label_region_clipped_by_border:
        reason = "A barcode or text line touches the frame edge; the label appears cut off."
        if scene.label_region_clipped_by_border and not (scene.barcode_touches_border or scene.text_truncated_at_border):
            reason = "The detected label region itself is clipped by the frame edge; the label appears cut off."
        return with_fields(Decision(
            status="FLAGGED", primary_flag="PARTIAL_PARCEL",
            flag_reason=reason,
            awb_suggestion=resolved.get("suggestion"),
        ))

    if scene.barcode_region_found_but_not_decoded:
        reason = "A label-like region was found but no barcode could be decoded from it, even after cropping and enhancement."
        if scene.label_region_low_confidence_text:
            reason = "A label-like region was found with only low-confidence text and no decodable barcode, consistent with the label being partially covered."
        return with_fields(Decision(
            status="FLAGGED", primary_flag="LABEL_BLOCKED",
            flag_reason=reason,
            awb_suggestion=resolved.get("suggestion"),
        ))

    if resolved["outcome"] == "conflicting":
        return with_fields(Decision(
            status="FLAGGED", primary_flag="CONFLICTING_READS", flag_reason=resolved["reason"],
            awb_suggestion=resolved["suggestion"],
        ))

    if resolved["outcome"] == "low_confidence":
        return with_fields(Decision(
            status="FLAGGED", primary_flag="LOW_CONFIDENCE_READ", flag_reason=resolved["reason"],
            awb_suggestion=resolved["suggestion"],
        ))

    quality_poor = quality is not None and quality.blur_score < BLUR_MIN and (
        quality.brightness < BRIGHTNESS_MIN or quality.brightness > BRIGHTNESS_MAX
    )
    no_text = ocr_line_count == 0 and not overlay.detected
    if quality_poor and no_text:
        return with_fields(Decision(
            status="FLAGGED", primary_flag="IMAGE_QUALITY_POOR",
            flag_reason="The image is too blurry or too dark/bright to read anything.",
        ))

    if scene.label_region_found:
        return with_fields(Decision(
            status="FLAGGED", primary_flag="LABEL_UNREADABLE",
            flag_reason="A label-like region was found but no AWB could be read from it.",
        ))

    return with_fields(Decision(
        status="FLAGGED", primary_flag="LABEL_NOT_FOUND",
        flag_reason="No barcode, label region, or readable text was found; the cause cannot be determined without a scene model.",
    ))
