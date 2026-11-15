"""parse_fields.py: weight/dimension/AWB string variants (docs/evaluation.md section 4)."""
import pytest

from app.pipeline.parse_fields import find_awb_candidates, parse_weight_and_dimensions
from app.pipeline.types import OcrLine


def line(text: str, conf: float = 0.95) -> OcrLine:
    return OcrLine(text=text, confidence=conf, bbox=[], source="full")


WEIGHT_CASES = [
    ("Wt: 0.5 Kg", 0.5),
    ("Weight: 500 gm", 0.5),
    ("Wt: 0.45", None),  # no unit -> not extracted
    ("Weight: 2.3 KG", 2.3),
    ("Dead Wt: 1.2kg", 1.2),
    ("Weight 450 g", 0.45),
    ("Weight: 0.5kgs", 0.5),
    ("Actual Weight: 0.9 kg", 0.9),
    ("Gross Weight: 3.0 kg", 3.0),
    ("Wt 45 kg", 45.0),  # heavy but within plausibility (<=50kg)
    ("Wt 70 kg", None),  # implausible for a parcel, discarded (see PLAUSIBLE_WEIGHT_KG_MAX)
    ("Wt 150 kg", None),  # implausible, discarded
    ("Wt 0.005 kg", None),  # implausible (too light), discarded
]

VOLUMETRIC_IGNORED_CASES = [
    "Vol Wt: 3.5 kg",
    "Volumetric Weight: 2.0 kg",
    "Vol. Wt. 4.4 Kg",
]

DIMENSION_CASES = [
    ("10x20x5 cm", (10.0, 20.0, 5.0)),
    ("10X20X5", (10.0, 20.0, 5.0)),
    ("100x200x50 mm", (10.0, 20.0, 5.0)),
    ("L:10 B:5 H:3", (10.0, 5.0, 3.0)),
    ("10*20*5", (10.0, 20.0, 5.0)),
    ("L 10 x B 20 x H 5 cm", (10.0, 20.0, 5.0)),
    ("Dim 15x10x8cm", (15.0, 10.0, 8.0)),
    ("20.5x13.9x15.6 cm", (20.5, 13.9, 15.6)),
    ("L:100 B:50 H:30 mm", (10.0, 5.0, 3.0)),
    ("4 x 6 x 250 cm", None),  # 250cm exceeds plausibility, discarded
    ("0x0x0 cm", None),  # zero, discarded
]

AWB_NEAR_KEYWORD_CASES = [
    ("AWB: 19100012345", "19100012345"),
    ("Waybill No 77000123456", "77000123456"),
    ("Tracking ID: 90100012345", "90100012345"),
    ("Docket: 19100012345", "19100012345"),
]

AWB_DIGIT_CONFUSION_CASES = [
    ("AWB: l9l00O1234S", "19100012345"),  # l->1, O->0, S->5 after repair
]

AWB_BARE_NUMERIC_CASES = [
    ("Random text 77500012345 more text", "77500012345"),  # BlueDart-shaped, bare
    ("Random text 12345 more text", None),  # too short, not courier-shaped -> no candidate
]


@pytest.mark.parametrize("text,expected_kg", WEIGHT_CASES)
def test_weight_variants(text, expected_kg):
    fields = parse_weight_and_dimensions([line(text)])
    if expected_kg is None:
        assert fields.weight_kg is None
    else:
        assert fields.weight_kg == pytest.approx(expected_kg)


@pytest.mark.parametrize("text", VOLUMETRIC_IGNORED_CASES)
def test_volumetric_weight_ignored(text):
    fields = parse_weight_and_dimensions([line(text)])
    assert fields.weight_kg is None
    assert "VOLUMETRIC_WEIGHT_IGNORED" in fields.warnings


def test_volumetric_then_dead_weight_both_present():
    fields = parse_weight_and_dimensions([line("Vol Wt: 3.5 kg Dead Wt: 1.2 kg")])
    assert fields.weight_kg == pytest.approx(1.2)
    assert "VOLUMETRIC_WEIGHT_IGNORED" in fields.warnings


@pytest.mark.parametrize("text,expected", DIMENSION_CASES)
def test_dimension_variants(text, expected):
    fields = parse_weight_and_dimensions([line(text)])
    if expected is None:
        assert fields.length_cm is None
        if any(ch.isdigit() for ch in text):
            assert fields.dimensions_raw is not None  # raw text preserved even when discarded
    else:
        length, width, height = expected
        assert fields.length_cm == pytest.approx(length)
        assert fields.width_cm == pytest.approx(width)
        assert fields.height_cm == pytest.approx(height)


@pytest.mark.parametrize("text,expected", AWB_NEAR_KEYWORD_CASES)
def test_awb_near_keyword(text, expected):
    candidates = find_awb_candidates([line(text)])
    values = [c.value for c in candidates]
    assert expected in values


@pytest.mark.parametrize("text,expected", AWB_DIGIT_CONFUSION_CASES)
def test_awb_digit_confusion_repair(text, expected):
    candidates = find_awb_candidates([line(text)])
    values = [c.value for c in candidates]
    assert expected in values
    repaired = next(c for c in candidates if c.value == expected)
    assert repaired.validated_by_pattern


@pytest.mark.parametrize("text,expected", AWB_BARE_NUMERIC_CASES)
def test_awb_bare_numeric(text, expected):
    candidates = find_awb_candidates([line(text)])
    values = [c.value for c in candidates]
    if expected is None:
        assert values == []
    else:
        assert expected in values


def test_empty_ocr_lines():
    assert find_awb_candidates([]) == []
    fields = parse_weight_and_dimensions([])
    assert fields.weight_kg is None
    assert fields.length_cm is None


def test_no_match_returns_empty():
    candidates = find_awb_candidates([line("Fragile handle with care")])
    assert candidates == []
    fields = parse_weight_and_dimensions([line("Fragile handle with care")])
    assert fields.weight_kg is None
    assert fields.dimensions_raw is None


def test_multiple_weight_mentions_first_valid_wins():
    fields = parse_weight_and_dimensions([line("Weight: 0.5 kg Net Weight: 0.6 kg")])
    assert fields.weight_kg == pytest.approx(0.5)


def test_awb_candidates_deduplicated():
    candidates = find_awb_candidates([line("AWB: 19100012345"), line("Tracking: 19100012345")])
    values = [c.value for c in candidates]
    assert values.count("19100012345") == 1
