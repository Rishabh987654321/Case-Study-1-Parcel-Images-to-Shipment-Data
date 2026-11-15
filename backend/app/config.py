"""All configuration in one place. Thresholds are named constants with env overrides."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# Upload / batch limits
MAX_FILE_MB = _float("MAX_FILE_MB", 15)
MAX_FILES_PER_BATCH = _int("MAX_FILES_PER_BATCH", 1000)
MAX_REQUEST_MB = _float("MAX_REQUEST_MB", 100)
MIN_IMAGE_SIDE = _int("MIN_IMAGE_SIDE", 300)
MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 12000 * 12000)  # PIL decompression-bomb guard
ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png"]

# Background processing (Phase 3; defined now so config is centralized)
_worker_count_env = os.environ.get("WORKER_COUNT", "").strip()
WORKER_COUNT = int(_worker_count_env) if _worker_count_env else max(1, (os.cpu_count() or 2) - 1)
IMAGE_TIMEOUT_S = _int("IMAGE_TIMEOUT_S", 60)
WORKING_MAX_SIDE = _int("WORKING_MAX_SIDE", 2000)
# Off by default only for fast unit tests that don't exercise processing (see
# backend/tests/conftest.py); the real app and any processing-focused test
# fixture leave this on.
ENABLE_WORKER_POOL = os.environ.get("ENABLE_WORKER_POOL", "1") == "1"

OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "rapidocr")
SCENE_PROVIDER = os.environ.get("SCENE_PROVIDER", "heuristic")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Paths (relative to the backend/ working directory the app is run from)
DATA_DIR = os.environ.get("DATA_DIR", "data")
UPLOAD_DIR = str(Path(DATA_DIR) / "uploads")
THUMBNAIL_DIR = str(Path(DATA_DIR) / "thumbnails")
DB_PATH = str(Path(DATA_DIR) / "app.db")
THUMBNAIL_MAX_SIDE = _int("THUMBNAIL_MAX_SIDE", 160)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

# Pipeline thresholds
BLUR_MIN = _float("BLUR_MIN", 100.0)
BRIGHTNESS_MIN = _float("BRIGHTNESS_MIN", 30.0)
BRIGHTNESS_MAX = _float("BRIGHTNESS_MAX", 240.0)
BORDER_MARGIN_PCT = _float("BORDER_MARGIN_PCT", 0.015)
PLAUSIBLE_WEIGHT_KG_MIN = _float("PLAUSIBLE_WEIGHT_KG_MIN", 0.01)
# 50kg (not 100kg) because this app's domain is parcels, not freight; the one
# 70kg reading observed in the dataset was on a small soft bag next to a
# "Barcode 2D: NoRead" sensor-failure flag (see "One more Ekart Format" in
# docs/dataset-notes.md) - treated as an implausible sensor reading, not a fact.
PLAUSIBLE_WEIGHT_KG_MAX = _float("PLAUSIBLE_WEIGHT_KG_MAX", 50.0)
PLAUSIBLE_DIM_CM_MIN = _float("PLAUSIBLE_DIM_CM_MIN", 1.0)
PLAUSIBLE_DIM_CM_MAX = _float("PLAUSIBLE_DIM_CM_MAX", 200.0)
AWB_OCR_MIN_CONF = _float("AWB_OCR_MIN_CONF", 0.90)

# Label-region localization (Phase 1 addition, see docs/dataset-notes.md section 2)
LABEL_MIN_AREA_PCT = _float("LABEL_MIN_AREA_PCT", 0.05)
LABEL_CROP_PADDING_PCT = _float("LABEL_CROP_PADDING_PCT", 0.12)
LABEL_UPSCALE_MIN_SIDE = _int("LABEL_UPSCALE_MIN_SIDE", 1000)
LABEL_MAX_UPSCALE = _float("LABEL_MAX_UPSCALE", 4.0)

PIPELINE_VERSION = "1.0.0"
