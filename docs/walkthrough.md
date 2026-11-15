# Live Review Walkthrough

One-page map from "can you change X right now?" to the exact file and function. Verified against the actual code on 2026-11-14, not against an assumed structure — a couple of rows below correct template assumptions that didn't match reality (noted inline).

| If asked to... | Edit this file | Specifically... |
| --- | --- | --- |
| Add a new flag code | `backend/app/pipeline/decide.py` | There is no `FlagCode` enum — `primary_flag` is just a `str \| None` on the `Decision` dataclass. Add the new condition directly in `decide()` (or whichever helper it calls), returning `Decision(status="FLAGGED", primary_flag="NEW_CODE", flag_reason="...", ...)`. Respect the priority order in `docs/flag_taxonomy.md` section 3 when deciding where the new check goes. |
| | `docs/flag_taxonomy.md` | Add a row to the flag table and, if it changes priority, to section 3. |
| | `README.md` | Update the Flag Taxonomy table if it's one of the common ones. |
| Change a confidence threshold | `backend/app/config.py` | `AWB_OCR_MIN_CONF`, `BLUR_MIN`, `BRIGHTNESS_MIN`/`MAX`, `PLAUSIBLE_WEIGHT_KG_MIN`/`MAX`, `PLAUSIBLE_DIM_CM_MIN`/`MAX`, `LABEL_MIN_AREA_PCT`, `BORDER_MARGIN_PCT` — all named constants with `_float()`/`_int()` env overrides. |
| | Or `.env` | Any of the above can be overridden without touching code, e.g. `AWB_OCR_MIN_CONF=0.95`. |
| Add a CSV column | `backend/app/api/export.py` | Add the column name to `CSV_COLUMNS` and the corresponding value to `_row_for()`'s return list (same position). Note: the file actually doing this is `api/export.py`, not a separate `services/csv_export.py` — that split doesn't exist in this codebase. |
| | `docs/data_model.md` | Update the column spec (section 3) — it already has a note explaining the Phase 2→3 column reshuffle, follow that pattern. |
| Add a new courier pattern | `backend/app/pipeline/couriers.yaml` | Add an entry: `name`, `awb_regex`, `awb_length`, `prefixes`, `barcode_types`, `checksum`, `notes` (see existing entries for the format). No code change needed — `courier_patterns.py` reads this file directly. |
| Change the OCR engine | `backend/app/pipeline/providers/` | Add a new provider file (e.g. `ocr_tesseract.py`) exposing a `run_ocr(image_bgr, source) -> list[OcrLine]` function, matching `ocr_rapid.py`'s shape. |
| | `backend/app/pipeline/ocr.py` | **Important:** `_default_provider()` currently *always* returns `ocr_rapid.run_ocr`, unconditionally — it does not read `config.OCR_PROVIDER` at all. `config.OCR_PROVIDER` exists and is reported via `GET /api/config`, but nothing dispatches on it yet. To actually make this switchable, you'd add `if config.OCR_PROVIDER == "tesseract": from .providers.ocr_tesseract import run_ocr; return run_ocr` here — this is new wiring, not flipping an existing switch. |
| | `backend/app/config.py` | `OCR_PROVIDER` setting already exists (currently inert — see above). |
| Adjust image size limits | `backend/app/config.py` | `MAX_FILE_MB`, `MIN_IMAGE_SIDE`, `MAX_IMAGE_PIXELS`, `WORKING_MAX_SIDE`. |
| | `backend/app/services/storage.py` | `_validate()` is what actually enforces `MAX_FILE_MB`/`MIN_IMAGE_SIDE`/`MAX_IMAGE_PIXELS` at upload time — worth opening alongside config.py if asked "where exactly does this get checked." |
| Change worker count | `.env` | `WORKER_COUNT=4` (blank = `cpu_count - 1`). Takes effect on next server restart — `WorkerPool` reads it once at construction in `app/main.py`'s lifespan. |
| Understand why image X got flag Y | Run the CLI on a one-image folder (it takes a **folder**, not a single file — there's no `--json -`/stdout option): `mkdir -p /tmp/one && cp sample_data/raw/X.jpg /tmp/one/ && python -m app.pipeline.cli /tmp/one --json /tmp/one/out.json && cat /tmp/one/out.json` | Full evidence tree printed: barcodes, OCR lines, overlay fields, quality metrics, scene signals, and the exact `flag_reason` string `decide()` produced. |
| Disable background processing (e.g. to inspect queued-but-unprocessed state) | `.env` | `ENABLE_WORKER_POOL=0` — images stay `queued` forever; used by the fast unit test fixture (`backend/tests/conftest.py`'s `client` fixture, as opposed to `processing_client`). |
| Change how many images process in parallel vs. memory used | `.env` | Same knob either way — `WORKER_COUNT` trades throughput for peak RSS (~7.1GB measured at `WORKER_COUNT=11`; see README's Key Tuning Knobs). |
