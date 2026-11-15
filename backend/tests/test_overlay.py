"""overlay.py: sorter-camera overlay parsing across the schema variants actually
observed in sample_data/raw (docs/dataset-notes.md section 2)."""
from app.pipeline.overlay import non_overlay_lines, parse_overlay
from app.pipeline.types import OcrLine


def lines(*texts: str) -> list[OcrLine]:
    return [OcrLine(text=t, confidence=0.95, bbox=[], source="full") for t in texts]


def test_not_detected_without_strong_marker():
    overlay = parse_overlay(lines("Fragile", "Handle with care"))
    assert overlay.detected is False
    assert overlay.awb is None


def test_yellow_schema_split_key_value_lines():
    overlay = parse_overlay(lines(
        "Location:", "Bangalore_Hoskote_GW (Karnataka)", "AWB No:", "19109110324413",
        "Length:", "62.900 cm", "Width:", "48.400 cm", "Height:", "45.400 cm",
        "R.Vol.:", "136231.000 cm (cubic)", "Weight:", "14400.000 gm", "Time:", "7/19/2025 9:38:47 PM",
    ))
    assert overlay.detected is True
    assert overlay.awb == "19109110324413"
    assert overlay.weight_kg == 14.4
    assert overlay.length_cm == 62.9 and overlay.width_cm == 48.4 and overlay.height_cm == 45.4


def test_white_red_schema_compact_lhw_mm():
    overlay = parse_overlay(lines(
        "Location: Delhi_Bilaspur", "Barcode:19108610817924", "Dimension:L0213XH0148XW0178",
        "Weight:01190", "Time:20250605034844086", "Sorter_ID:DA03",
    ))
    assert overlay.detected is True
    assert overlay.awb == "19108610817924"
    assert overlay.weight_kg == 1.19
    assert overlay.length_cm == 21.3 and overlay.height_cm == 14.8 and overlay.width_cm == 17.8


def test_beardo_schema_weight_kg_key_unit():
    overlay = parse_overlay(lines(
        "LOCATIONCODE:ITG", "AWB NO :77549916382", "LENGTH(cm) : 36.10", "WIDTH(cm) : 24.90",
        "HEIGHT(cm) : 12.90", "WEIGHT(Kg) : 1.33", "DATETIME:16-06-202519:10:28.220", "ID:01",
    ))
    assert overlay.detected is True
    assert overlay.awb == "77549916382"
    assert overlay.weight_kg == 1.33


def test_green_mid_schema_actual_weight_grams_ignores_volumetric():
    overlay = parse_overlay(lines(
        "MID: 34982", "Date Time: 2025-07-20 18:12:27",
        "L: 56.8 cm A.W: 7140 g", "W: 55.5 cm V.W: 56743.2 g", "H: 18 cm",
        "AWB: 191109110324435",
    ))
    assert overlay.detected is True
    assert overlay.weight_kg == 7.14
    assert "VOLUMETRIC_WEIGHT_IGNORED" in overlay.warnings


def test_zero_dimensions_discarded():
    overlay = parse_overlay(lines("Barcode: PROC0001161070", "Weight: 0.37 kg", "L * W * H:  0000 * 0000 * 0000"))
    assert overlay.length_cm is None
    assert "DIMENSIONS_UNCERTAIN" in overlay.warnings
    assert overlay.dimensions_raw is not None


def test_implausible_weight_discarded():
    overlay = parse_overlay(lines(
        "Location: YKB_North_Zone", "Barcode 1D 473362_473362-s203019:PR0C0001129074",
        "Weight: 70.0 kg", "R. Vol.: 9558 cm (cubic)",
    ))
    assert overlay.weight_kg is None
    assert "WEIGHT_UNCERTAIN" in overlay.warnings


def test_barcode_semicolon_composite_prefers_courier_match():
    overlay = parse_overlay(lines("Index:1814", "Barcode:217191936;19109110322534", "BDN:NG"))
    assert overlay.awb == "19109110322534"


def test_barcode_underscore_composite_prefers_courier_match():
    # observed OCR misread "Barcode" as "Barc0de" (zero for letter-o)
    overlay = parse_overlay(lines("Index:620", "Barc0de:41306503_19109110324251", "BDN:NG"))
    assert overlay.awb == "19109110324251"


def test_non_overlay_lines_empty_when_everything_is_overlay_vocabulary():
    all_lines = lines(
        "Location:", "Chandigarh_Rajpura_GW (Punjab)", "AWB No:", "19108610815360",
        "Length:", "20.8 cm", "Width:", "15.3 cm", "Height:", "16.7 cm",
        "R.Vol.:", "4724 cm (cubic)", "Weight:", "1.21 kg", "Time:", "08-06-2025 18:43:50",
    )
    assert non_overlay_lines(all_lines) == []


def test_non_overlay_lines_finds_product_text():
    all_lines = lines("Location: EPU", "AWB_No: 77846471776", "ARAMYA Weekly New Launches", "Premium Fabrics")
    independent = non_overlay_lines(all_lines)
    assert any("ARAMYA" in line.text for line in independent)
