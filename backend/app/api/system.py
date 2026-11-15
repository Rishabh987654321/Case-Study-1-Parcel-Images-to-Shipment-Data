from fastapi import APIRouter

from app.config import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_MB,
    MAX_FILES_PER_BATCH,
    MAX_REQUEST_MB,
    OCR_PROVIDER,
    PIPELINE_VERSION,
    SCENE_PROVIDER,
)
from app.schemas import (
    ConfigResponse,
    HealthResponse,
    LimitsResponse,
    ProvidersResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=PIPELINE_VERSION)


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(
        limits=LimitsResponse(
            max_file_mb=MAX_FILE_MB,
            max_files_per_batch=MAX_FILES_PER_BATCH,
            max_request_mb=MAX_REQUEST_MB,
            allowed_types=ALLOWED_CONTENT_TYPES,
        ),
        providers=ProvidersResponse(ocr=OCR_PROVIDER, scene=SCENE_PROVIDER, scene_available=["heuristic"]),
        pipeline_version=PIPELINE_VERSION,
    )
