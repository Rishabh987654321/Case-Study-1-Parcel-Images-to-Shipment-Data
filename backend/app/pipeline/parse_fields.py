"""Stage: field extraction from the printed courier label's OCR text (not the
sorter overlay - that is overlay.py). Rules, not an LLM, per docs/flag_taxonomy.md.
"""
import re

from app.config import (
    PLAUSIBLE_DIM_CM_MAX,
    PLAUSIBLE_DIM_CM_MIN,
    PLAUSIBLE_WEIGHT_KG_MAX,
    PLAUSIBLE_WEIGHT_KG_MIN,
)
from app.pipeline.courier_patterns import is_awb_shaped, match_courier
from app.pipeline.types import AwbCandidate, OcrLine, ParsedFields

_AWB_KEYWORDS = r"(?:AWB|Waybill|Tracking(?:\s*ID)?|Docket|Airway|Ref(?:erence)?|CN)"
_AWB_NEAR_KEYWORD_PATTERN = re.compile(_AWB_KEYWORDS + r"[\s\w]{0,15}?:?\s*([A-Z0-9]{8,20})", re.IGNORECASE)
_BARE_NUMERIC_PATTERN = re.compile(r"\b([0-9]{8,16})\b")

_DIGIT_CONFUSION = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"})

_WEIGHT_KEYWORDS = r"(?:dead\s*w(?:eigh)?t|actual\s*w(?:eigh)?t|gross\s*w(?:eigh)?t|w(?:eigh)?t)"
_VOL_MARKER = re.compile(r"\bvol(?:umetric)?\b", re.IGNORECASE)
_WEIGHT_PATTERN = re.compile(
    _WEIGHT_KEYWORDS + r"\s*[:.\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*(kgs?|gms?|g)\b", re.IGNORECASE
)

# "10x20x5 cm", "10X20X5", "100x200x50 mm", "10*20*5", "L:10 B:5 H:3", "L 10 x B 20 x H 5 cm"
_DIM_XSEP_PATTERN = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*(cm|mm|in|inch)?",
)
_DIM_LBH_PATTERN = re.compile(
    r"L\s*:?\s*([0-9]+(?:\.[0-9]+)?)\D{0,6}?B\s*:?\s*([0-9]+(?:\.[0-9]+)?)\D{0,6}?H\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(cm|mm|in|inch)?",
    re.IGNORECASE,
)


def _to_kg(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("kg"):
        return value
    return value / 1000.0  # g / gm / gms


def _to_cm(value: float, unit: str | None) -> float:
    if not unit:
        return value
    unit = unit.lower()
    if unit == "mm":
        return value / 10.0
    if unit in ("in", "inch"):
        return value * 2.54
    return value


def _plausible_weight(kg: float) -> bool:
    return PLAUSIBLE_WEIGHT_KG_MIN <= kg <= PLAUSIBLE_WEIGHT_KG_MAX


def _plausible_dim(cm: float) -> bool:
    return PLAUSIBLE_DIM_CM_MIN <= cm <= PLAUSIBLE_DIM_CM_MAX


def find_awb_candidates(ocr_lines: list[OcrLine]) -> list[AwbCandidate]:
    """Scan label OCR text for AWB-shaped strings near a keyword, or bare numeric
    strings that already match a courier pattern."""
    candidates: list[AwbCandidate] = []
    seen: set[str] = set()
    text = " ".join(line.text for line in ocr_lines)
    mean_conf = sum(line.confidence for line in ocr_lines) / len(ocr_lines) if ocr_lines else 0.0

    for m in _AWB_NEAR_KEYWORD_PATTERN.finditer(text):
        raw = m.group(1)
        value, validated = _validate_or_repair(raw)
        if value in seen:
            continue
        seen.add(value)
        courier = match_courier(value)
        confidence = mean_conf if validated else mean_conf * 0.5
        candidates.append(
            AwbCandidate(
                value=value,
                source="ocr",
                confidence=confidence,
                validated_by_pattern=validated,
                courier_match=courier.name if courier else None,
            )
        )

    for m in _BARE_NUMERIC_PATTERN.finditer(text):
        raw = m.group(1)
        if raw in seen:
            continue
        courier = match_courier(raw)
        if courier is None:
            continue  # bare numbers only count as candidates when a specific courier pattern matches
        seen.add(raw)
        candidates.append(
            AwbCandidate(
                value=raw,
                source="ocr",
                confidence=mean_conf,
                validated_by_pattern=True,
                courier_match=courier.name,
            )
        )

    return candidates


def _validate_or_repair(raw: str) -> tuple[str, bool]:
    if is_awb_shaped(raw):
        return raw, True
    repaired = raw.translate(_DIGIT_CONFUSION)
    if repaired != raw and is_awb_shaped(repaired):
        return repaired, True
    return raw, False


def parse_weight_and_dimensions(ocr_lines: list[OcrLine]) -> ParsedFields:
    fields = ParsedFields()
    text = " ".join(line.text for line in ocr_lines)

    scan_from = 0
    for m in _WEIGHT_PATTERN.finditer(text):
        start = m.start()
        window = text[max(scan_from, start - 15) : start]
        scan_from = m.end()
        if _VOL_MARKER.search(window) or _VOL_MARKER.search(m.group(0)):
            fields.warnings.append("VOLUMETRIC_WEIGHT_IGNORED")
            continue
        value = float(m.group(1).replace(",", "."))
        kg = _to_kg(value, m.group(2))
        if _plausible_weight(kg):
            fields.weight_kg = kg
            fields.weight_raw = m.group(0)
        else:
            fields.weight_raw = m.group(0)
            fields.warnings.append("WEIGHT_UNCERTAIN")
        break  # first (non-volumetric) weight mention wins

    m = _DIM_LBH_PATTERN.search(text)
    if not m:
        m = _DIM_XSEP_PATTERN.search(text)
    if m:
        unit = m.group(4)
        length, width, height = (_to_cm(float(g), unit) for g in m.groups()[:3])
        if all(_plausible_dim(v) for v in (length, width, height)):
            fields.length_cm, fields.width_cm, fields.height_cm = length, width, height
            fields.dimensions_raw = m.group(0)
        else:
            fields.dimensions_raw = m.group(0)
            fields.warnings.append("DIMENSIONS_UNCERTAIN")

    return fields
