# Architecture: Case Study 1 (Parcel Images to Shipment Data)

## 1. Goal and non-goals

**Goal.** A web app where a warehouse user bulk-uploads parcel photos (hundreds), the system reads each courier label in the background, and the user views and downloads one structured record per image (AWB/tracking number, weight, dimensions) or an honest status flag.

**Priorities (from the brief's scoring).** (1) Works end to end on unseen images with honest flags. (2) Sound judgment and stated assumptions. (3) Readable, runnable code. (4) Clear README and ability to explain and change it live. Polish is NOT scored.

**Non-goals.** Authentication, multi-user accounts, cloud deployment, model training, manual correction UI (list as future work), cases 2 and 3.

## 2. Guiding principles

1. **Abstain over guess.** A wrong AWB is worse than a flag. Every extracted field carries a source and a confidence; weak evidence means null plus a flag.
2. **Deterministic first, models second.** Barcodes and regex-validated OCR text do the extraction. Any model (VLM/CLIP) is optional and only used for scene judgments (no parcel, multiple parcels, blocked label), never to invent digits.
3. **Free and local by default.** No API key needed. Optional providers are off by default and the app must work without them.
4. **Simple enough to explain.** No Celery, Redis, Docker requirement or message broker. SQLite plus a worker pool is enough.
5. **Generalize.** They will run unseen images with possibly different couriers. Do not hard-code to the sample dataset; derive patterns from data in Phase 0 but keep rules generic and configurable.

## 3. Tech stack

| Layer | Choice | Why | Alternative |
| --- | --- | --- | --- |
| Backend API | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 | Familiar (your FastAPI/Django experience), typed, auto docs at `/docs` | Django REST |
| Storage | SQLite (WAL mode) via SQLAlchemy 2.0, files on local disk | Zero setup, persistent across restarts, enough for hundreds of images | PostgreSQL |
| Background work | In-process DB-backed queue + `ProcessPoolExecutor` workers | OCR is CPU-bound; survives page close; no broker | Celery + Redis |
| Barcode decode | `zxing-cpp` (pip wheel, 1D and 2D, multiple per image) with OpenCV pre-processing retries | Barcode is the most reliable source for AWB; no system DLLs | `pyzbar` (needs zbar lib) |
| OCR | `rapidocr-onnxruntime` default (pip only, models bundled, CPU) behind an interface | Light install, works on Windows | EasyOCR (heavy torch), Tesseract (needs system install) |
| Image handling | Pillow + OpenCV (headless) + NumPy | Standard | |
| Scene judgment (optional) | `SCENE_PROVIDER=none \| heuristic \| ollama \| clip` | Chosen by evaluation in Phase 5; default must need no download | Gemini free tier (key required, off by default) |
| Frontend | React + TypeScript + Vite, TanStack Query for polling, Tailwind CSS | Your stack; minimal | |
| Tests | pytest (backend), Vitest optional (frontend) | | |
| Run | `scripts/run.ps1` and `scripts/run.sh` (create venv, install, build frontend, start on one port) | Under 15 minutes from clean clone | Docker compose as optional extra |

OCR and barcode libraries must be **confirmed in a Phase 0 spike** on 20+ real images before committing. Pin versions in `requirements.txt`.

## 4. System diagram

```
Browser (React)
  | 1. POST /api/batches                      -> batch_id
  | 2. POST /api/batches/{id}/images (chunks of ~10 files, 2-3 in parallel)
  | 3. POST /api/batches/{id}/finalize
  | 4. GET  /api/batches/{id}  (poll every 2s)  + GET .../records
  | 5. GET  /api/batches/{id}/export.csv
  v
FastAPI app (one process)
  |-- API layer: validation, limits, error format
  |-- Storage service: saves originals, makes thumbnails, sha256 dedupe
  |-- SQLite: batches, images, results
  |-- Queue service: marks images 'queued', workers claim rows atomically
  |-- Worker pool (N processes): runs the pipeline per image, writes result row
  v
Pipeline (pure functions, no web code; also runnable as a CLI)
  load -> quality -> barcode -> ocr -> parse fields -> scene signals -> decide -> result
```

## 5. Pipeline stages (per image)

Input: path to an image. Output: a `ResultRecord` (see `docs/data_model.md`). Each stage is a separate module with unit tests. The CLI `python -m app.pipeline.cli <folder>` runs the pipeline without the web app; this is how accuracy is evaluated early.

1. **Load and validate.** Open with Pillow, verify it is a real image (not just by extension), apply EXIF orientation, convert to RGB, reject if corrupt, or smaller than a minimum size (e.g. shorter side < 300 px). Downscale a working copy to a max side (default 2000 px) to bound time and memory; keep original for display.
2. **Quality metrics.** Blur (variance of Laplacian), brightness/contrast, resolution. Used for flags and confidence, never to silently alter results.
3. **Label-region localization (Phase 1 addition).** Phase 0 found only 2/20 images decode a barcode on the full downscaled frame, because the label is a small region in a wide sorter shot. A brightness + contour heuristic (`label_detect.py`) finds the largest plausible label/parcel blob, crops it with padding, and upscales it (up to 4x, to at least 1000 px on the short side) before barcode/OCR retry. Heuristic only, not a scene classifier - it is allowed to pick the wrong blob (e.g. an empty conveyor) on edge cases; see `docs/dataset-notes.md`.
4. **Barcode detection and decode.** Try the full image, then the label crop, then retries on the crop: grayscale + CLAHE, adaptive threshold, and rotations (90/180/270) when nothing decodes. Collect every barcode: value, symbology, bounding polygon (mapped back to working-image coordinates), whether it touches the image border. Keep all, because labels often have several barcodes (AWB, order id, routing code).
5. **OCR.** Run OCR on the full working image and, if a label region was found, also on the cropped+upscaled label for better small-text accuracy. Collect lines with text, confidence, bounding box. If very little text is found, retry at other rotations.
6. **Overlay parsing (Phase 1 addition).** Most images in this dataset carry a warehouse sorter-camera text overlay burned into the frame, separate from the printed courier label - structured key:value text reporting AWB/weight/dimensions (`overlay.py`). Treated as a third, independent evidence channel alongside barcode and label OCR (see `docs/flag_taxonomy.md` section 4): reliable when present, but plausibility-checked like any other source, since the sorter's own sensor reading can be stale or wrong.
7. **Field parsing (rules, not LLM).**
   - AWB candidates from barcodes and from OCR text near keywords (AWB, Waybill, Tracking, Docket). Validate with generic patterns learned from the dataset (length, digit/alpha structure, courier prefixes). Barcode value confirmed by OCR text = high confidence.
   - Weight: keyword (weight/wt/dead/actual) + number + unit (kg, g). Normalize to kg. Ignore volumetric weight for `weight_kg` (store as a warning/raw note).
   - Dimensions: patterns like `L x B x H`, `10x20x5 cm`, `L:10 B:5 H:3`. Normalize to cm (convert mm/in).
   - Digit-confusion repair (O to 0, I/l to 1, S to 5, B to 8) only inside fields that must be numeric and only if the repaired value passes validation.
   - Plausibility limits (configurable): weight 0.01 to 50 kg (parcels, not freight - see `backend/app/pipeline/couriers.yaml`); each dimension 1 to 200 cm.
8. **Scene signals.** Deterministic signals first (barcode touching border, truncated text lines, barcode detected but not decodable, count of distinct AWB-like barcodes, label-region found). Optional provider (VLM or CLIP) adds `parcel_count`, `label_visible`, `label_occluded`, `partially_visible` with its own confidence. See Phase 5.
9. **Decide.** Apply the decision procedure in `docs/flag_taxonomy.md` to produce `status` (OK / FLAGGED / ERROR), one primary flag, secondary warnings, and the final field values. This is the only module that decides; other stages only produce evidence.
10. **Persist.** Store the final fields plus raw evidence (barcodes, OCR lines, overlay, metrics, pipeline version) so a reviewer can see why.

Post-batch step: **duplicate AWB check** across the batch (same AWB in two images adds a `DUPLICATE_AWB` warning to both).

## 6. Batch lifecycle

```
Batch:  created -> uploading -> processing -> completed | completed_with_errors | cancelled
Image:  uploaded -> queued -> processing -> done | error      (rejected files never enter the queue)
```

- Images become `queued` as soon as their upload succeeds, so processing overlaps with uploading.
- `finalize` tells the server no more files are coming. If a tab closes mid-upload and finalize never arrives, a batch with all images terminal and idle for 5 minutes is reported as completed when read.
- **Restart safety.** On startup, images stuck in `processing` go back to `queued`.
- **Atomic claim.** A worker claims a row with a single `UPDATE ... WHERE status='queued'` so two workers never take the same image.
- **Timeouts.** Per-image timeout (default 60 s). On timeout or exception the image becomes `error` with `PROCESSING_ERROR`; the batch continues.
- **Cancel / retry.** Cancel stops claiming new images. Retry-failed requeues `error` images.
- **Concurrency.** Worker count defaults to `max(1, cpu_count - 1)`, configurable. Limit memory by processing one image per worker at a time and downscaling early.

## 7. Optional enhanced path (off by default)

| Provider | Needs | Used for | Notes |
| --- | --- | --- | --- |
| `heuristic` (default) | nothing | border/partial, multiple barcodes, no-label-found | Honest umbrella flag `LABEL_NOT_FOUND` when it cannot tell why |
| `ollama` | Ollama installed locally + a small vision model pulled | parcel_count, label_visible, occluded | Slow on CPU; call only on images that need scene judgment |
| `clip` | `transformers`/`open_clip` and a first-run model download | zero-shot "no parcel / hand over label" | Evaluate accuracy before enabling |

`GET /api/config` reports which providers are active so the UI and README stay honest. If an optional provider fails or is missing, the pipeline falls back to `heuristic` and records that in the result's `pipeline_notes`.

## 8. Repo layout

```
case1-parcel-labels/
  AGENTS.md  README.md  .env.example  .gitignore
  docs/                      # all the .md files from this kit
  backend/
    requirements.txt  pyproject.toml (ruff, pytest config)
    app/
      main.py config.py db.py models.py schemas.py errors.py
      api/        batches.py images.py export.py system.py
      services/   storage.py queue.py worker.py csv_export.py thumbnails.py
      pipeline/   cli.py runner.py types.py preprocess.py quality.py
                  label_detect.py barcode.py ocr.py overlay.py parse_fields.py
                  scene.py decide.py courier_patterns.py couriers.yaml
                  providers/ (ocr_rapid.py, ocr_tesseract.py, scene_ollama.py, scene_clip.py)
    tests/        unit tests + tests/fixtures (tiny images)
    data/         (gitignored) uploads, thumbnails, app.db
  frontend/       (Vite + React + TS)
  eval/           ground_truth.csv  run_eval.py  reports/
  sample_data/    small subset of images + the outputs produced from them
  scripts/        run.ps1  run.sh  dev.ps1  dev.sh
```

## 9. Security and robustness

- Validate files by content (Pillow open + verify), not by extension or the client MIME type. Allow JPG/JPEG/PNG (WebP optional).
- Limits (configurable): max file size 15 MB, max 1000 images per batch, max total upload per request 100 MB, max image dimensions 12000 px (guard against decompression bombs via `Image.MAX_IMAGE_PIXELS`).
- Store files under generated ids; never use the client filename as a path (keep it only as display text). Prevent path traversal.
- CSV export guards against spreadsheet formula injection (prefix cells beginning with `=`, `+`, `-`, `@` with a single quote) and writes UTF-8 with BOM.
- CORS limited to the dev frontend origin; in production the frontend is served from the same origin.
- No secrets in the repo; `.env.example` only.
- Errors return the JSON shape in `docs/api.md`; stack traces go to logs, not responses.

## 10. Performance targets (measure, then report honestly)

- Throughput on a normal laptop CPU: aim for about 2 to 4 seconds per image per worker; 300 images should finish in well under 15 minutes with 4 workers.
- UI stays responsive: uploads chunked, results paginated (e.g. 50 per page), thumbnails for the table (e.g. 160 px), originals loaded on demand.
- Record measured timings in the README (do not promise numbers that were not measured).

## 11. Main risks and mitigations

| Risk | Mitigation |
| --- | --- |
| OCR misreads digits | AWB mainly from barcodes; OCR-only AWB accepted only with strict validation and high confidence, otherwise suggestion column only |
| Cannot distinguish no parcel / blocked label / unreadable with free tools | Umbrella flag `LABEL_NOT_FOUND` by default; refine with optional provider if evaluation shows it is reliable |
| Unseen couriers or label layouts | Generic patterns, configurable `couriers.yaml`, evaluation with augmented images |
| Slow processing on CPU | Downscale early, process rotations only on failure, process pool, per-image timeout |
| Excel mangles long numeric AWBs | Document it; CSV has AWB as text and a README note on importing the column as Text |
| Memory blowup on huge batches | One image per worker, downscale, stream CSV |
