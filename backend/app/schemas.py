"""Pydantic v2 request/response shapes mirroring docs/api.md."""
from pydantic import BaseModel, ConfigDict


class BatchCreate(BaseModel):
    name: str | None = None


class BatchSummary(BaseModel):
    batch_id: str
    name: str | None
    status: str
    finalized: bool
    created_at: str
    total_images: int
    rejected_count: int
    processed: int
    progress_pct: float
    eta_seconds: int | None
    counts: dict[str, int]
    flag_counts: dict[str, int]


class UploadAccepted(BaseModel):
    image_id: str
    name: str
    warnings: list[str] = []


class UploadRejected(BaseModel):
    name: str
    code: str
    message: str


class UploadResponse(BaseModel):
    accepted: list[UploadAccepted]
    rejected: list[UploadRejected]


class ResultRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_id: str
    image_name: str
    status: str
    primary_flag: str | None
    flag_reason: str | None
    warnings: list[str]
    awb: str | None
    awb_source: str | None
    awb_confidence: float | None
    awb_suggestion: str | None
    weight_kg: float | None
    weight_raw: str | None
    dimensions_cm: dict[str, float] | None
    dimensions_raw: str | None
    courier: str | None
    confidence: float
    processing_ms: int
    thumbnail_url: str


class ResultDetail(ResultRecord):
    evidence: dict
    image_url: str


class PaginatedRecords(BaseModel):
    items: list[ResultRecord]
    page: int
    page_size: int
    total: int


class PaginatedBatches(BaseModel):
    items: list[BatchSummary]
    page: int
    page_size: int
    total: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail


class LimitsResponse(BaseModel):
    max_file_mb: float
    max_files_per_batch: int
    max_request_mb: float
    allowed_types: list[str]


class ProvidersResponse(BaseModel):
    ocr: str
    scene: str
    scene_available: list[str]


class ConfigResponse(BaseModel):
    limits: LimitsResponse
    providers: ProvidersResponse
    pipeline_version: str


class HealthResponse(BaseModel):
    status: str
    version: str


class FinalizeResponse(BaseModel):
    status: str


class CancelResponse(BaseModel):
    status: str


class RetryFailedResponse(BaseModel):
    requeued: int
