"""Shared fixtures: an isolated DB + upload/thumbnail dirs per test, via tmp_path,
so API tests never touch the real data/ directory."""
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from sqlalchemy.orm import sessionmaker

import app.config as config_module
import app.main as main_module
from app.api import export as export_module
from app.db import Base, get_db, make_engine
from app.main import app
from app.services import storage
from app.services import worker as worker_module

TEST_WORKER_COUNT = 2
TEST_IMAGE_TIMEOUT_S = 30


def _build_client(tmp_path, monkeypatch, *, enable_worker_pool: bool):
    db_path = tmp_path / "test.db"
    engine = make_engine(str(db_path))
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(storage, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(storage, "THUMBNAIL_DIR", str(tmp_path / "thumbnails"))

    # Every module that does `from app.db import SessionLocal` at import time
    # bound its own name to the *production* sessionmaker; patch each one so
    # the worker-pool coordinator thread and the CSV export generator (neither
    # of which go through FastAPI's Depends(get_db)) hit the test DB too.
    monkeypatch.setattr(main_module, "SessionLocal", TestSession)
    monkeypatch.setattr(worker_module, "SessionLocal", TestSession)
    monkeypatch.setattr(export_module, "SessionLocal", TestSession)
    monkeypatch.setattr(main_module, "ENABLE_WORKER_POOL", enable_worker_pool)

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    client.SessionLocal = TestSession  # lets tests seed/inspect rows directly
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fast fixture for tests that don't need real background processing - no
    worker subprocesses are started, so these stay quick (used by the Phase 1/2
    tests and most Phase 3 API-shape tests)."""
    test_client = _build_client(tmp_path, monkeypatch, enable_worker_pool=False)
    with test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def processing_client(tmp_path, monkeypatch):
    """Starts the real worker pool (subprocesses included) for integration
    tests that need images to actually get processed. Pinned to a small worker
    count so each test doesn't pay for spinning up cpu_count-1 OCR-loaded
    subprocesses just to process a handful of images."""
    from app.api import batches as batches_module

    monkeypatch.setattr(config_module, "WORKER_COUNT", TEST_WORKER_COUNT)
    monkeypatch.setattr(config_module, "IMAGE_TIMEOUT_S", TEST_IMAGE_TIMEOUT_S)
    monkeypatch.setattr(batches_module, "WORKER_COUNT", TEST_WORKER_COUNT)
    test_client = _build_client(tmp_path, monkeypatch, enable_worker_pool=True)
    with test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_jpeg_bytes(width: int = 400, height: int = 400, color=(200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buf, format="JPEG")
    return buf.getvalue()


def make_png_bytes(width: int = 400, height: int = 400, color=(50, 200, 50)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def wait_for_batch_status(client, batch_id: str, statuses: tuple[str, ...], timeout_s: float = 90.0, interval_s: float = 0.5) -> dict:
    """Polls GET /batches/{id} the same way the real frontend would."""
    deadline = time.perf_counter() + timeout_s
    last = None
    while time.perf_counter() < deadline:
        last = client.get(f"/api/batches/{batch_id}").json()
        if last["status"] in statuses:
            return last
        time.sleep(interval_s)
    raise TimeoutError(f"batch {batch_id} did not reach {statuses} within {timeout_s}s (last seen: {last})")


SAMPLE_RAW_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "raw"


def sample_image_paths(n: int) -> list[Path]:
    files = sorted(p for p in SAMPLE_RAW_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if len(files) < n:
        raise RuntimeError(f"sample_data/raw has only {len(files)} images, need {n}")
    return files[:n]
