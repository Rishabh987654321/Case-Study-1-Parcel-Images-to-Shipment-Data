"""Data classes shared by every pipeline stage. Pure Python, no web/DB imports."""
from dataclasses import dataclass, field
from typing import Literal

Point = tuple[float, float]
BarcodeSource = Literal["original", "crop", "enhanced"]
OcrSource = Literal["full", "crop", "overlay"]
AwbSource = Literal["barcode", "ocr", "overlay"]
Status = Literal["OK", "FLAGGED", "ERROR"]


@dataclass
class PipelineInput:
    image_path: str
    image_id: str


@dataclass
class QualityMetrics:
    blur_score: float
    brightness: float
    contrast: float
    width: int
    height: int


@dataclass
class BarcodeResult:
    value: str
    symbology: str
    bbox_polygon: list[Point]
    touches_border: bool
    source_image: BarcodeSource


@dataclass
class OcrLine:
    text: str
    confidence: float
    bbox: list[Point]
    source: OcrSource


@dataclass
class OverlayData:
    awb: str | None = None
    weight_raw: str | None = None
    weight_kg: float | None = None
    dimensions_raw: str | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    raw_text: str = ""
    detected: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class AwbCandidate:
    value: str
    source: AwbSource
    confidence: float
    validated_by_pattern: bool
    courier_match: str | None = None


@dataclass
class ParsedFields:
    awb: str | None = None
    awb_source: str | None = None
    awb_confidence: float = 0.0
    awb_suggestion: str | None = None
    weight_kg: float | None = None
    weight_raw: str | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    dimensions_raw: str | None = None
    courier: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class LabelRegionInfo:
    """Serializable record of a detected label crop (the crop pixels themselves are not kept)."""
    bbox_xywh: tuple[int, int, int, int]
    confidence: float
    upscale_factor: float


@dataclass
class SceneSignals:
    barcode_touches_border: bool = False
    text_truncated_at_border: bool = False
    distinct_awb_barcode_count: int = 0
    label_region_found: bool = False
    barcode_region_found_but_not_decoded: bool = False
    parcel_present: bool = True
    # Phase 5 additions (docs/flag_taxonomy.md section 2 NO_PARCEL/MULTIPLE_PARCELS/
    # PARTIAL_PARCEL/LABEL_BLOCKED signals, strengthened without a model dependency):
    distinct_label_regions: int = 0
    distinct_ocr_awb_regions: int = 0
    label_region_clipped_by_border: bool = False
    label_region_low_confidence_text: bool = False


@dataclass
class PipelineEvidence:
    quality: QualityMetrics | None = None
    barcodes: list[BarcodeResult] = field(default_factory=list)
    ocr_lines: list[OcrLine] = field(default_factory=list)
    overlay: OverlayData = field(default_factory=OverlayData)
    label_region: LabelRegionInfo | None = None
    awb_candidates: list[AwbCandidate] = field(default_factory=list)
    parsed_fields: ParsedFields = field(default_factory=ParsedFields)
    scene_signals: SceneSignals = field(default_factory=SceneSignals)
    timings: dict[str, float] = field(default_factory=dict)
    load_error: str | None = None
    pipeline_notes: list[str] = field(default_factory=list)


@dataclass
class ResultRecord:
    image_id: str
    filename: str
    status: Status
    primary_flag: str | None
    flag_reason: str | None
    warnings: list[str]
    awb: str | None
    awb_suggestion: str | None
    awb_source: str | None
    awb_confidence: float
    weight_kg: float | None
    weight_raw: str | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None
    dimensions_raw: str | None
    courier: str | None
    confidence: float
    evidence: PipelineEvidence
    pipeline_version: str
    processing_ms: int
    processed_at: str
