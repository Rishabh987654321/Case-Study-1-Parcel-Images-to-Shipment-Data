"""Stage: parse the warehouse sorter-camera text overlay (see docs/dataset-notes.md
section 2). This is a third, independent evidence channel alongside barcode and
label OCR. It is structured key:value text burned into the frame by the sorter's
own system, not the printed courier label - very reliable when present, but it can
be stale (AWB shown over an empty belt) or report implausible sensor readings
(0x0x0 dimensions, 70kg on a soft parcel), so every value is plausibility-checked
before being trusted.

At least five overlay schema variants were observed; rather than detect "the"
schema, this module runs every known field pattern against the concatenated OCR
text and keeps the first match per field. A handful of literal example strings
(not invented) drive the regexes - see the "observed:" comments.
"""
import re

from app.config import (
    PLAUSIBLE_DIM_CM_MAX,
    PLAUSIBLE_DIM_CM_MIN,
    PLAUSIBLE_WEIGHT_KG_MAX,
    PLAUSIBLE_WEIGHT_KG_MIN,
)
from app.pipeline.courier_patterns import is_awb_shaped, match_courier
from app.pipeline.types import OcrLine, OverlayData

# Any one of these appearing means "this frame has a sorter overlay" (distinct from
# plain printed-label text, which never contains these exact field names).
_STRONG_MARKERS = re.compile(
    r"(Sorter_ID|R\.\s*Vol|LOCATION\s*CODE|MID\s*:|BDN\s*:|AWB[_\s]*No|AWB_NO|A\.W\s*:|V\.W\s*:|"
    r"Barc[o0]de\s*:|Scan\s*Time|L\s*\*\s*W\s*\*\s*H|Dim\(L)",
    re.IGNORECASE,
)

# observed: "AWB No: | 19109110324413", "AWB_No: | 77846471776", "AWBNo: | 77573777455",
#           "AWB_NO : 77558439335" (printed-label-looking but inside an overlay block)
_AWB_PATTERNS = [
    re.compile(r"AWB[_\s]*No\.?\s*:?[\s|]*([0-9]{8,16})", re.IGNORECASE),
]
# observed: "Barcode:19108610817924" (single), "Barcode:217191936;19109110322534" (composite,
# semicolon-separated) and "Barc0de:41306503_19109110324251" (composite, underscore-separated)
_BARCODE_AWB_PATTERN = re.compile(r"Barc[o0]de\s*:?[\s|]*([0-9]{6,16})(?:[;,_]([0-9]{6,16}))?", re.IGNORECASE)

# observed: "Weight: | 0.45 kg"
_WEIGHT_KG_PATTERN = re.compile(r"Weight\s*:?[\s|]*([0-9]{1,3}(?:[.,][0-9]{1,3})?)\s*(?:kg|kgs)\b", re.IGNORECASE)
# observed: "WEIGHT(Kg) : 1.33" - unit is in the key, value has no trailing unit
_WEIGHT_KG_KEYUNIT_PATTERN = re.compile(r"WEIGHT\(Kg\)\s*:?[\s|]*([0-9]{1,3}(?:[.,][0-9]{1,3})?)", re.IGNORECASE)
_WEIGHT_GRAM_PATTERN = re.compile(r"(?<!V\.)(?<!V)Weight\s*:?[\s|]*([0-9]{2,6}(?:[.,][0-9]+)?)\s*(?:gm|gms|g)\b", re.IGNORECASE)
# observed: "Weight:01190" with no unit at all (schema always reports grams, zero-padded)
_WEIGHT_NO_UNIT_PATTERN = re.compile(r"(?<!V\.)(?<!V)Weight\s*:?[\s|]*([0-9]{3,6})(?!\s*[.\d])(?!\s*(?:kg|g|gm|cm|mm))", re.IGNORECASE)
_ACTUAL_WEIGHT_GRAM_PATTERN = re.compile(r"A\.?W\.?\s*:?[\s|]*([0-9]{2,6}(?:[.,][0-9]+)?)\s*g\b", re.IGNORECASE)
_VOLUMETRIC_MARKER = re.compile(r"\bV\.?\s*W\.?\s*:|Vol(?:umetric)?\s*Wt\b", re.IGNORECASE)

# observed: "Length: | 62.900 cm" + "Width: | 48.400 cm" + "Height: | 45.400 cm"
_LEN_CM_PATTERN = re.compile(r"Length\s*:?[\s|]*([0-9]+(?:\.[0-9]+)?)\s*cm", re.IGNORECASE)
_WID_CM_PATTERN = re.compile(r"Width\s*:?[\s|]*([0-9]+(?:\.[0-9]+)?)\s*cm", re.IGNORECASE)
_HGT_CM_PATTERN = re.compile(r"Height\s*:?[\s|]*([0-9]+(?:\.[0-9]+)?)\s*cm", re.IGNORECASE)
# observed: "Dimension(LxBxH): 15.5x11.1x7.7 cm"
_DIM_LBH_CM_PATTERN = re.compile(
    r"Dimension\s*\(?L?x?B?x?H?\)?\s*:?[\s|]*([0-9.]+)\s*[xX]\s*([0-9.]+)\s*[xX]\s*([0-9.]+)\s*cm", re.IGNORECASE
)
# observed: "Dimension:L0213XH0148XW0178" (mm, order is L, H, W)
_DIM_LHW_MM_PATTERN = re.compile(r"\bL\s*(\d{3,5})X?H\s*(\d{3,5})X?W\s*(\d{3,5})\b", re.IGNORECASE)
# observed: "Dim(L/W/H):0658/0402/0243mm"
_DIM_SLASH_MM_PATTERN = re.compile(r"Dim\(L/W/H\)\s*:?[\s|]*(\d{2,5})/(\d{2,5})/(\d{2,5})\s*mm", re.IGNORECASE)
# observed: "Dimension: | 0217 X 0143 X 0168" (mm, L,W,H order, no unit)
_DIM_PLAIN_MM_PATTERN = re.compile(r"Dimension\s*:?[\s|]*(\d{3,5})\s*[Xx]\s*(\d{3,5})\s*[Xx]\s*(\d{3,5})\b", re.IGNORECASE)
# observed: "L * W * H:  0000 * 0000 * 0000" (mm, L,W,H order, no unit)
_DIM_LWH_STAR_PATTERN = re.compile(r"L\s*\*\s*W\s*\*\s*H\s*:?[\s|]*(\d{1,5})\s*\*\s*(\d{1,5})\s*\*\s*(\d{1,5})", re.IGNORECASE)


def _plausible_weight(kg: float) -> bool:
    return PLAUSIBLE_WEIGHT_KG_MIN <= kg <= PLAUSIBLE_WEIGHT_KG_MAX


def _plausible_dim(cm: float) -> bool:
    return PLAUSIBLE_DIM_CM_MIN <= cm <= PLAUSIBLE_DIM_CM_MAX


# A line is "overlay vocabulary" if it names a known overlay field, or is a bare
# value shape (number, unit, date/time, location-code) that overlay fields use.
_OVERLAY_KEYWORD_LINE = re.compile(
    r"(Location|AWB[_\s]*No\.?|AWB_NO|Barc[o0]de(\s*[12]D)?|NoRead|Dimension|Length|Width|Height|Weight|"
    r"R\.?\s*Vol\.?|Volume|Time|Sorter_ID|MID|BDN|Date\s*Time|A\.?W\.?|V\.?W\.?|ID|LOCATION\s*CODE|"
    r"LENGTH\(cm\)|WIDTH\(cm\)|HEIGHT\(cm\)|WEIGHT\(Kg\)|DATETIME|Index)",
    re.IGNORECASE,
)
_OVERLAY_VALUE_LINE = re.compile(
    r"^[\d.,/:\s-]+\s*(cm3?|kgs?|gm?s?|mm)?\s*(\(\w+\))?$"  # numbers, dims-with-unit, dates, times, "4724 cm (cubic)"
    r"|^\w+[_-]\w+.*\(.*\)$"  # "Bangalore_Hoskote_GW (Karnataka)" style location
    r"|^[A-Z]{2,4}[0-9]{0,2}$"  # short sorter/location codes like "DA1", "BDB2", "ITG"
    r"|^\d{2,5}[Xx]\d{2,5}[Xx]\d{2,5}$"  # Phase 5: "0217X0143X0168" - bare LxWxH dimension value with no unit, its own OCR line
    r"|^\w+\)$",  # Phase 5: a trailing fragment like "Bengal)" - OCR sometimes emits a wrapped location line twice, once in full and once as just the tail; a bare word+")" with no matching "(" is overlay noise, not independent text
    re.IGNORECASE,
)


def non_overlay_lines(ocr_lines: list[OcrLine]) -> list[OcrLine]:
    """OCR lines that are not explained by the sorter overlay's own vocabulary -
    used to judge whether there is any evidence of a parcel independent of the
    overlay (see scene.py). A line counts as independent only if it is reasonably
    long and matches neither the overlay keyword list nor a bare overlay value shape.
    """
    independent = []
    for line in ocr_lines:
        text = line.text.strip()
        if len(text) < 4:
            continue
        if _OVERLAY_KEYWORD_LINE.search(text) or _OVERLAY_VALUE_LINE.match(text):
            continue
        independent.append(line)
    return independent


def parse_overlay(ocr_lines: list[OcrLine]) -> OverlayData:
    text = " | ".join(line.text for line in ocr_lines)
    overlay = OverlayData(raw_text=text)

    if not _STRONG_MARKERS.search(text):
        return overlay
    overlay.detected = True

    awb = None
    for pattern in _AWB_PATTERNS:
        m = pattern.search(text)
        if m:
            awb = m.group(1)
            break
    if awb is None:
        m = _BARCODE_AWB_PATTERN.search(text)
        if m:
            candidates = [g for g in m.groups() if g]
            # prefer whichever group matches a SPECIFIC courier pattern over one that
            # only satisfies the generic alphanumeric fallback; else the longest
            awb = next((c for c in candidates if match_courier(c)), None) or max(candidates, key=len)
    if awb and is_awb_shaped(awb):
        overlay.awb = awb

    weight_kg = None
    weight_raw = None
    m = _WEIGHT_KG_PATTERN.search(text) or _WEIGHT_KG_KEYUNIT_PATTERN.search(text)
    if m:
        weight_raw = m.group(0)
        weight_kg = float(m.group(1).replace(",", "."))
    else:
        m = _WEIGHT_GRAM_PATTERN.search(text) or _ACTUAL_WEIGHT_GRAM_PATTERN.search(text)
        if m:
            weight_raw = m.group(0)
            weight_kg = float(m.group(1).replace(",", ".")) / 1000.0
        else:
            m = _WEIGHT_NO_UNIT_PATTERN.search(text)
            if m:
                weight_raw = m.group(0)
                weight_kg = float(m.group(1)) / 1000.0  # schema always reports grams here
    if _VOLUMETRIC_MARKER.search(text):
        overlay.warnings.append("VOLUMETRIC_WEIGHT_IGNORED")
    if weight_kg is not None:
        if _plausible_weight(weight_kg):
            overlay.weight_kg = weight_kg
            overlay.weight_raw = weight_raw
        else:
            overlay.weight_raw = weight_raw
            overlay.warnings.append("WEIGHT_UNCERTAIN")

    dims = None
    dims_raw = None
    m = _DIM_LBH_CM_PATTERN.search(text)
    if m:
        dims_raw = m.group(0)
        dims = tuple(float(g) for g in m.groups())  # already cm, L/W/H order
    else:
        m = _DIM_SLASH_MM_PATTERN.search(text)
        if m:
            dims_raw = m.group(0)
            dims = tuple(int(g) / 10.0 for g in m.groups())  # mm -> cm, L/W/H order
        else:
            m = _DIM_LHW_MM_PATTERN.search(text)
            if m:
                dims_raw = m.group(0)
                length, height, width = (int(g) / 10.0 for g in m.groups())  # order is L,H,W in this schema
                dims = (length, width, height)
            else:
                lw_hits = [_LEN_CM_PATTERN.search(text), _WID_CM_PATTERN.search(text), _HGT_CM_PATTERN.search(text)]
                if all(lw_hits):
                    dims_raw = " / ".join(h.group(0) for h in lw_hits)
                    dims = tuple(float(h.group(1)) for h in lw_hits)  # already cm
                else:
                    m = _DIM_PLAIN_MM_PATTERN.search(text) or _DIM_LWH_STAR_PATTERN.search(text)
                    if m:
                        dims_raw = m.group(0)
                        dims = tuple(int(g) / 10.0 for g in m.groups())  # mm -> cm, L/W/H order

    if dims is not None:
        length_cm, width_cm, height_cm = dims
        if all(_plausible_dim(v) for v in dims):
            overlay.length_cm, overlay.width_cm, overlay.height_cm = length_cm, width_cm, height_cm
            overlay.dimensions_raw = dims_raw
        else:
            overlay.dimensions_raw = dims_raw
            overlay.warnings.append("DIMENSIONS_UNCERTAIN")

    return overlay
