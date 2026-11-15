"""FastAPI app entry point.

Run from backend/:
    uvicorn app.main:app --reload --port 8000
"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image as PILImage

from app.api import batches, export, images, records, system
from app.config import (
    CORS_ORIGINS,
    DATA_DIR,
    ENABLE_WORKER_POOL,
    MAX_IMAGE_PIXELS,
    MAX_REQUEST_MB,
    THUMBNAIL_DIR,
    UPLOAD_DIR,
)
from app.db import SessionLocal, create_all
from app.errors import AppError
from app.services import queue
from app.services.worker import WorkerPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

PILImage.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

worker_pool: WorkerPool | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global worker_pool
    for d in (DATA_DIR, UPLOAD_DIR, THUMBNAIL_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)
    create_all()

    db = SessionLocal()
    try:
        queue.recover_stuck_images(db)
    finally:
        db.close()

    if ENABLE_WORKER_POOL:
        worker_pool = WorkerPool()
        worker_pool.start()

    yield

    if worker_pool is not None:
        worker_pool.stop()
        worker_pool = None


app = FastAPI(title="Parcel Label Reader API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_REQUEST_MB * 1024 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "REQUEST_TOO_LARGE", "message": f"Request body exceeds the {MAX_REQUEST_MB:.0f} MB limit.", "details": {}}},
        )
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(AppError)
def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "The request could not be validated.", "details": {"errors": exc.errors()}}},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong on our side. Please try again.", "details": {}}},
    )


app.include_router(system.router, prefix="/api")
app.include_router(batches.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(records.router, prefix="/api")
app.include_router(export.router, prefix="/api")

# Serves the built frontend (frontend/dist, see scripts/run.sh) on the same
# port as the API. Registered last so every /api/* route above still matches
# first; only requests that fall through to here (frontend routes, assets)
# reach the SPA fallback. Absent in dev (vite serves the frontend on :5173
# instead, see scripts/dev.sh) and in tests, where frontend/dist was never built.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "favicon.svg")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(FRONTEND_DIST / "index.html")
