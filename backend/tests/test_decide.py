"""decide.py: table-driven, one case per flag code and per AWB acceptance rule
(docs/flag_taxonomy.md)."""
from app.pipeline.decide import decide
from app.pipeline.types import (
    AwbCandidate,
    BarcodeResult,
    OverlayData,
    ParsedFields,
    QualityMetrics,
    SceneSignals,
)

Q_GOOD = QualityMetrics(blur_score=500, brightness=120, contrast=50, width=2000, height=1500)
Q_POOR = QualityMetrics(blur_score=10, brightness=10, contrast=5, width=2000, height=1500)
SCENE_DEFAULT = SceneSignals(parcel_present=True)
NO_OVERLAY = OverlayData()
NO_FIELDS = ParsedFields()


def barcode(value: str, touches_border: bool = False) -> BarcodeResult:
    return BarcodeResult(value=value, symbology="Code128", bbox_polygon=[], touches_border=touches_border, source_image="original")


def test_ok_barcode_and_overlay_agree():
    overlay = OverlayData(detected=True, awb="19109999999999")
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, overlay, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "OK"
    assert d.awb == "19109999999999"
    assert d.awb_source == "barcode+overlay"
    assert d.confidence == 0.98


def test_ok_barcode_and_ocr_agree():
    ocr = [AwbCandidate(value="19109999999999", source="ocr", confidence=0.9, validated_by_pattern=True)]
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, NO_OVERLAY, ocr, NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "OK"
    assert d.awb_source == "both"
    assert d.confidence == 0.95


def test_ok_barcode_only_single_awb_like():
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, NO_OVERLAY, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "OK"
    assert d.awb_source == "barcode"
    assert d.confidence == 0.80


def test_ok_overlay_only_parcel_present():
    overlay = OverlayData(detected=True, awb="19109999999999")
    d = decide(None, Q_GOOD, [], 10, overlay, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "OK"
    assert d.awb_source == "overlay"
    assert d.confidence == 0.80


def test_flagged_no_parcel_overlay_awb_but_no_parcel():
    overlay = OverlayData(detected=True, awb="19109999999999")
    scene = SceneSignals(parcel_present=False)
    d = decide(None, Q_GOOD, [], 10, overlay, [], NO_FIELDS, scene)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "NO_PARCEL"
    assert d.awb is None


def test_flagged_multiple_parcels_two_distinct_barcodes():
    d = decide(None, Q_GOOD, [barcode("19109999999999"), barcode("19100000000001")], 5, NO_OVERLAY, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "MULTIPLE_PARCELS"


def test_flagged_partial_parcel_barcode_touches_border():
    scene = SceneSignals(parcel_present=True, barcode_touches_border=True)
    d = decide(None, Q_GOOD, [], 2, NO_OVERLAY, [], NO_FIELDS, scene)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "PARTIAL_PARCEL"


def test_flagged_label_blocked_region_found_not_decoded():
    scene = SceneSignals(parcel_present=True, label_region_found=True, barcode_region_found_but_not_decoded=True)
    d = decide(None, Q_GOOD, [], 2, NO_OVERLAY, [], NO_FIELDS, scene)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "LABEL_BLOCKED"


def test_flagged_conflicting_reads_barcode_vs_overlay():
    overlay = OverlayData(detected=True, awb="19100000000001")
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, overlay, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "CONFLICTING_READS"
    assert "19109999999999" in d.awb_suggestion
    assert "19100000000001" in d.awb_suggestion


def test_flagged_low_confidence_read_ocr_only():
    ocr = [AwbCandidate(value="19109999999999", source="ocr", confidence=0.6, validated_by_pattern=True)]
    d = decide(None, Q_GOOD, [], 5, NO_OVERLAY, ocr, NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "LOW_CONFIDENCE_READ"
    assert d.awb_suggestion == "19109999999999"


def test_flagged_label_not_found_nothing_at_all():
    d = decide(None, Q_GOOD, [], 0, NO_OVERLAY, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "LABEL_NOT_FOUND"


def test_flagged_label_unreadable_region_found_nothing_read():
    scene = SceneSignals(parcel_present=True, label_region_found=True)
    d = decide(None, Q_GOOD, [barcode("x")], 0, NO_OVERLAY, [], NO_FIELDS, scene)
    # barcode "x" isn't AWB-shaped, so no barcode AWB; falls through to label_region_found
    assert d.status == "FLAGGED"
    assert d.primary_flag == "LABEL_UNREADABLE"


def test_flagged_image_quality_poor_blur_and_dark_no_text():
    d = decide(None, Q_POOR, [], 0, NO_OVERLAY, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "FLAGGED"
    assert d.primary_flag == "IMAGE_QUALITY_POOR"


def test_error_image_corrupt():
    d = decide("truncated file", None, [], 0, NO_OVERLAY, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "ERROR"
    assert d.primary_flag == "IMAGE_CORRUPT"


def test_ok_overlay_and_ocr_agree_no_barcode():
    overlay = OverlayData(detected=True, awb="19109999999999")
    ocr = [AwbCandidate(value="19109999999999", source="ocr", confidence=0.9, validated_by_pattern=True)]
    d = decide(None, Q_GOOD, [], 10, overlay, ocr, NO_FIELDS, SCENE_DEFAULT)
    assert d.status == "OK"
    assert d.awb_source == "ocr+overlay"
    assert d.confidence == 0.95


def test_fields_carried_through_on_ok():
    overlay = OverlayData(detected=True, awb="19109999999999", weight_kg=0.5, weight_raw="0.5 kg", length_cm=10, width_cm=20, height_cm=5, dimensions_raw="10x20x5")
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, overlay, [], NO_FIELDS, SCENE_DEFAULT)
    assert d.weight_kg == 0.5
    assert d.length_cm == 10 and d.width_cm == 20 and d.height_cm == 5


def test_warnings_merged_from_overlay_and_label_fields():
    overlay = OverlayData(detected=True, awb="19109999999999", warnings=["DIMENSIONS_UNCERTAIN"])
    fields = ParsedFields(warnings=["VOLUMETRIC_WEIGHT_IGNORED"])
    d = decide(None, Q_GOOD, [barcode("19109999999999")], 5, overlay, [], fields, SCENE_DEFAULT)
    assert "DIMENSIONS_UNCERTAIN" in d.warnings
    assert "VOLUMETRIC_WEIGHT_IGNORED" in d.warnings
