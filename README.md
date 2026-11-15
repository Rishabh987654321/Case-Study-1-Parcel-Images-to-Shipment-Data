# Case Study 1: Parcel Images to Shipment Data

### What it does

A warehouse user bulk-uploads parcel photos (hundreds at a time) through a web app; in the background, the system reads each courier label — AWB (tracking number), weight, and dimensions — using barcode decoding, OCR, and a warehouse sorter-camera text overlay, cross-validates the evidence, and either records a trustworthy result or honestly flags what it couldn't read (never a guessed value). The whole batch is reviewable in a results table and downloadable as one CSV.

**Prerequisites:** Python 3.11+, Node.js 18+, npm

**Option A: One command (recommended)**

```bash
# macOS / Linux
chmod +x scripts/run.sh && ./scripts/run.sh

# Windows (PowerShell)
.\scripts\run.ps1
```

**Option B: Manual setup**

```bash
# Backend (one venv at the repo root, shared with the test suite)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# Frontend
cd frontend
npm install
npm run build

# Start (serves both on one port)
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

**Development mode** (hot reload):

```bash
./scripts/dev.sh   # or .\scripts\dev.ps1
# Backend: http://localhost:8000  |  Frontend (Vite, proxies /api): http://localhost:5173
```

**Measured timing:** a full clean-state run (`.venv`, `frontend/node_modules`, `frontend/dist`, and `backend/data` all deleted first, then `./scripts/run.sh` to a serving app) took **6m 30s** on the development machine (12-vCPU Linux/WSL2) with warm pip/npm package caches. A fully offline network download of the ~400MB of Python wheels (onnxruntime, opencv, rapidocr) will add time on a slow connection, but this leaves comfortable margin under the 15-minute target even accounting for that.

### How it works

**Architecture:**

```
Browser (React) --> FastAPI --> SQLite (batches/images/results) + DB-backed queue
                                      |
                                      v
                         Worker pool (N processes, default cpu_count-1)
                                      |
                                      v
     Pipeline (pure functions, also runnable as a CLI):
     preprocess -> quality -> label detect -> barcode -> OCR -> overlay parse
                 -> field parse -> scene signals -> decide -> result
```

Three independent extraction channels feed the decision step:

- **Barcode** (most reliable when it decodes — but see Known Limitations, decode rate is low)
- **Sorter-camera overlay text** (very reliable when present — most images in this dataset carry one; see below)
- **Label OCR** (the printed courier label itself)

`decide()` (`backend/app/pipeline/decide.py`) is the only module that turns evidence into a verdict: it cross-validates the three channels, accepts an AWB as `OK` only when the evidence clears one of a fixed set of confidence rules (agreement between two channels, or a single channel matching a known courier pattern), and flags everything else — never averaging or guessing between disagreeing values.

**The "abstain over guess" principle:**
A wrong AWB is worse than a flag. The pipeline has **12 flag codes** (see table below) and puts any unverified candidate number in a separate `awb_suggestion` column for human review — it never goes into the confirmed `awb` column unless the evidence clears a validation rule.

**Overlay parsing:**
Most images in this dataset carry a warehouse sorter-camera text overlay burned into the frame — not printed on the courier label, but added by the sorter's own camera system, reporting AWB/weight/dimensions it already measured. It's parsed as a first-class extraction source (`backend/app/pipeline/overlay.py`) alongside barcodes and label OCR. But it's the sorter's own sensor reading, not ground truth: it can be **stale** (showing a previous parcel's AWB over an empty belt) or **implausible** (`0x0x0` dimensions, a weight far outside a parcel's normal range). Every overlay value goes through the same plausibility checks as any other source before being trusted.

### Evaluation Results

From `eval/reports/report_20261113.md` (ground truth: 38 hand-labeled images; real numbers, not invented; updated after Phase 5/6 scene-signal work - see that report's "Phase 5: before vs after" and "Phase 6" sections for the full before/after story):

| Metric                                         | Full set (n=38)                     | Held-out split (n=10)           |
| ---------------------------------------------- | ----------------------------------- | ------------------------------- |
| Wrong-extraction rate (target 0%)              | **3.7%** (1 / 27 predicted-OK rows) | 14.3% (1 / 7 predicted-OK rows) |
| AWB recall on readable images                  | 81.2% (of 32 truth-OK images)       | 75.0% (of 8 truth-OK images)    |
| Silent-miss rate (truth FLAGGED, predicted OK) | 16.7%                               | 50.0%                           |
| Weight accuracy (within 0.01kg)                | 30/32                               | 7/8                             |
| Dimension accuracy (within 0.5cm)              | 22/27                               | 5/7                             |

**Flag distribution** (predicted, full 262-image `sample_data/raw` dataset - not just the 38 labeled ones, from a fresh full run): OK 180, FLAGGED 82 (NO_PARCEL 52, LOW_CONFIDENCE_READ 22, PARTIAL_PARCEL 8), ERROR 0.

**Per-image timing** (from the Phase 3 load test processing the full 262-image dataset, `WORKER_COUNT=11` default on a 12-vCPU host): mean **20.1s**/image, p95 **39.8s**/image, under full 11-way concurrent CPU load. For comparison, a single process running OCR alone measures ~1.5s/image — the gap is CPU contention from running `WORKER_COUNT` OCR-loaded processes at once on fewer real cores than that; see `backend/app/pipeline/providers/ocr_rapid.py`'s comment for the exact numbers that led to pinning each worker's OCR thread pool to 1 thread (first attempted without pinning: ~26s/image under 8 unpinned workers).

**Total batch time for 262 images:** ~395-414s (about 6.5-7 min) of CLI processing wall time with 11 workers on the full re-runs done during Phase 5/6 (slightly higher than Phase 3's 204s API load test figure, consistent with these later runs also computing extra Phase 5/6 scene signals) — still comfortably under the architecture doc's "well under 15 minutes" target.

**Known wrong case** (the full set's only remaining wrong-extraction case - the numerator of the 3.7% figure above):

**`Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png`** — truth: FLAGGED/MULTIPLE*PARCELS (two distinct parcels — a "Sparify" box and a "MYFITNESS" box — in one frame). Predicted: OK, AWB `31049520637826`, which belongs to only one of the two parcels. Root cause: multiple-parcel detection counts distinct AWB-shaped \_barcodes* and, as of Phase 5, distinct label-shaped regions and distinct AWB-shaped OCR text; none of those fire here because the second parcel's only independent evidence is its _brand-name text_ ("MYFITNE\"", "Explore"), not a second region or number a heuristic can count. Still an open, honestly-documented limitation (see Known Limitations below).

The _other_ originally-known wrong case, `No Shipment ccaptured_png...` (stale overlay over an empty platform), is fixed - it no longer returns a wrong `OK`. It now lands on `FLAGGED/LOW_CONFIDENCE_READ` rather than the "more correct" `FLAGGED/NO_PARCEL`, because Phase 6 found that treating _every_ overlay-only, label-region-found case as a flat "no parcel" cost real recall at full-dataset scale (see the eval report's Phase 6 section) - a deliberate, documented trade-off, not an oversight.

### Flag Taxonomy

| Flag code                  | Meaning                                                            | Example                             |
| -------------------------- | ------------------------------------------------------------------ | ----------------------------------- |
| `NO_PARCEL`                | No parcel in frame (empty belt/platform)                           | `No Shipment packet captured...png` |
| `PARTIAL_PARCEL`           | Parcel or label cut off by the frame edge                          | `Half shipment captured...png`      |
| `MULTIPLE_PARCELS`         | 2+ parcels in frame, read would be ambiguous                       | `Multiple shipment packets...png`   |
| `LABEL_BLOCKED`            | Label covered by a hand/object/tape                                | —                                   |
| `LABEL_UNREADABLE`         | Label visible but too blurry/glared/small to read                  | —                                   |
| `LABEL_NOT_FOUND`          | No label located and the cause can't be determined (umbrella flag) | —                                   |
| `LOW_CONFIDENCE_READ`      | An AWB candidate exists but evidence is too weak to trust          | `One more Ekart Format...png`       |
| `CONFLICTING_READS`        | Barcode and OCR/overlay disagree on the AWB                        | —                                   |
| `AMBIGUOUS_AWB`            | Multiple AWB-like numbers, none confirmable                        | —                                   |
| `IMAGE_QUALITY_POOR`       | Too blurry/dark/low-res to analyze at all                          | —                                   |
| `IMAGE_CORRUPT` (ERROR)    | File can't be opened as an image                                   | —                                   |
| `PROCESSING_ERROR` (ERROR) | Timeout or unexpected exception                                    | —                                   |

Full taxonomy, priority order, and AWB acceptance rules: `docs/flag_taxonomy.md`.

### CSV Output

The web app's `GET /api/batches/{id}/export.csv` produces 18 columns, in this order:

`image_name, status, primary_flag, flag_reason, awb, awb_suggestion, awb_source, awb_confidence, weight_kg, weight_raw, length_cm, width_cm, height_cm, dimensions_raw, warnings, processed_at, pipeline_version, image_id`

- UTF-8 with BOM (opens correctly in Excel without a manual encoding step)
- Formula-injection guarded (`=`, `+`, `-`, `@`-prefixed cells get a leading `'`)
- **Excel note:** AWB numbers (11–15 digits) may display in scientific notation (e.g. `1.23E+15`) when a CSV is opened directly, because Excel auto-formats long numeric-looking cells. To preserve the full number: open the CSV, select the AWB/AWB-suggestion columns, format as **Text**, then re-import (or use Excel's "From Text/CSV" import wizard and set those columns to Text at import time). This is an Excel display limitation — the CSV itself contains the correct full-precision value as text.

Note: `sample_data/demo_output.csv` (see "Sample Data" below) was produced by the Phase 1 CLI directly rather than the web app, and uses a slightly different (18-column, differently-ordered) layout — see `docs/data_model.md` for both specs.

### Sample Data

`sample_data/demo_inputs/` has 12 real images from the dataset, picked to cover every flag category that actually occurs plus one deliberately-truncated file (no naturally-corrupt file exists in this dataset, so `corrupt_example_truncated.jpg` demonstrates the ERROR/`IMAGE_CORRUPT` path on purpose): clean OK reads (barcode-confirmed and overlay-confirmed), `NO_PARCEL`, `PARTIAL_PARCEL`, and the two known-wrong cases from Evaluation Results above (included deliberately, not hidden). `sample_data/demo_output.csv` and `sample_data/demo_output.json` are the Phase 1 CLI's actual output for exactly these 12 images — `.json` includes the full evidence tree (barcodes, OCR lines, overlay, quality metrics) for each one, so a reviewer can see what the system does without running anything.

### Configuration

All variables, with defaults, from `.env.example`:

| Variable                      | Default                 | Meaning                                                                                                                                                                                                 |
| ----------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MAX_FILE_MB`                 | 15                      | Max size per uploaded image                                                                                                                                                                             |
| `MAX_FILES_PER_BATCH`         | 1000                    | Max images per batch                                                                                                                                                                                    |
| `MAX_REQUEST_MB`              | 100                     | Max total size of one upload request                                                                                                                                                                    |
| `MIN_IMAGE_SIDE`              | 300                     | Reject images smaller than this (px, shorter side)                                                                                                                                                      |
| `MAX_IMAGE_PIXELS`            | 144000000 (12000×12000) | PIL decompression-bomb guard                                                                                                                                                                            |
| `WORKER_COUNT`                | blank → `cpu_count - 1` | Background worker processes                                                                                                                                                                             |
| `ENABLE_WORKER_POOL`          | 1                       | 0 disables background processing (used by fast unit tests)                                                                                                                                              |
| `IMAGE_TIMEOUT_S`             | 60                      | Per-image processing timeout before it's marked ERROR                                                                                                                                                   |
| `WORKING_MAX_SIDE`            | 2000                    | Downscale working copy to this max side (bounds time/memory)                                                                                                                                            |
| `THUMBNAIL_MAX_SIDE`          | 160                     | Thumbnail size shown in the results table                                                                                                                                                               |
| `OCR_PROVIDER`                | rapidocr                | Reserved for a future pluggable OCR backend — only `rapidocr` is wired up today                                                                                                                         |
| `SCENE_PROVIDER`              | heuristic               | `heuristic` (free, default) \| `ollama` \| `clip` — anything other than `heuristic` currently falls back to it with a `SCENE_PROVIDER_UNAVAILABLE` warning (not yet implemented, see Known Limitations) |
| `OLLAMA_URL` / `OLLAMA_MODEL` | localhost:11434 / blank | Only used if `SCENE_PROVIDER=ollama` is ever implemented                                                                                                                                                |
| `DATA_DIR`                    | `data`                  | Where uploads/thumbnails/the SQLite DB live                                                                                                                                                             |
| `LOG_LEVEL`                   | INFO                    | Python logging level                                                                                                                                                                                    |
| `CORS_ORIGINS`                | `http://localhost:5173` | Allowed origins (dev frontend only; production serves same-origin)                                                                                                                                      |

**Key tuning knobs:**

- **`WORKER_COUNT`** — reduce on low-memory machines. The Phase 3 load test measured **~7.1GB peak RSS with 11 workers** (each loads its own OCR model into memory). On an 8GB machine, try `WORKER_COUNT=3` or `4`.
- **`IMAGE_TIMEOUT_S`** — increase if you see images landing in ERROR with "Processing timed out" under full worker load; the load test saw 3/262 images (1.1%) hit the default 60s timeout under 11-way concurrency, and all 3 succeeded on a plain retry (`POST /retry-failed`) once contention eased.
- **`SCENE_PROVIDER`** — `heuristic` is the only implemented option; it's what distinguishes "no parcel" from "label blocked" using deterministic signals only (see Known Limitations for where this falls short).

### What I would improve with more time

1. **A real scene-recognition model** — this is no longer a hypothetical suggestion: a 3-image zero-shot CLIP (`ViT-B-32`, openai weights) spot check in Phase 5 correctly classified the empty-platform case as empty and the multiple-parcels case as multiple, both ahead of the single-parcel alternative - exactly the two hard cases the deterministic heuristics above still can't fully resolve. Not yet production-viable: no full ground-truth evaluation was run (the task's own bar for keeping a provider), and model load took ~200s, which would need per-worker-process caching (same pattern as `ocr_rapid.py`'s singleton engine) before it's practical at scale.
2. **A dedicated barcode-region detector** — `label_detect.py` is a general-purpose label-region heuristic; a detector trained/tuned specifically to find small barcodes within a wide frame would likely raise the barcode decode rate well above the 10% (2/20 images) Phase 0 measured on the full frame before cropping existed (see Known Limitations — the post-crop rate hasn't been separately re-measured).
3. **More ground truth** — 38 labeled images caught real systemic issues (the overlay-staleness and multi-parcel gaps above) but isn't enough for statistically confident recall/precision numbers; 200+ would be.
4. **A manual correction UI** — let a reviewer fix a FLAGGED result's AWB/weight/dimensions directly in the browser and feed that correction back into the record (and ideally into future ground truth), rather than only exporting the flag for an offline fix.
5. **A production-grade task queue** — the current `ProcessPoolExecutor`-based worker pool works well for hundreds of images on one machine, but a real multi-machine deployment would want a proper broker (Celery/RQ + Redis) so processing isn't tied to the single API process's lifetime.
6. **Docker Compose** — for a true one-command deployment that doesn't depend on the reviewer's local Python/Node versions at all.

### Known Limitations

- Without a scene-recognition model, the system cannot reliably distinguish between: no parcel in frame, a label completely hidden/facing away, and a fully blocked label. These all get `LABEL_NOT_FOUND` as an honest umbrella flag rather than a specific (possibly wrong) guess.
- **Stale/uncorroborated overlay data**: when the sorter overlay is the _only_ evidence (no barcode, no independently-read label text), the system never asserts a confirmed `OK` - it abstains to `NO_PARCEL` or `LOW_CONFIDENCE_READ` instead (which one depends on whether a label-shaped region was also found; see Evaluation Results above). Measured on the full 262-image dataset: 26% of all images hit this path. Whether a given one of those is a genuinely empty/stale frame or a real parcel the system just couldn't independently confirm isn't something this deterministic approach can always tell apart - that's exactly the gap a scene-recognition model would close (see "What I would improve" above and the Phase 5 CLIP finding: a 3-image zero-shot spot check correctly classified both the empty-platform and multiple-parcel hard cases, but wasn't evaluated at full rigor against ground truth, and model load time (~200s) would need caching per worker process before it's production-viable).
- **Multiple parcels** are only detected when 2+ distinct AWB-shaped barcodes decode, or 2+ separate label regions are found. A photo of two parcels with no decoded barcodes can be treated as a single parcel. Known affected case: `Multiple shipment packets in single sorter images_png...`.
- **Barcode decode rate is low.** The Phase 0 spike measured only 2/20 images (10%) decoding a barcode on the full downscaled frame, which is why `label_detect.py` (crop + upscale the label region before retrying) was built in Phase 1 — but the _post-crop_ decode rate across the full dataset hasn't been separately re-measured, so that specific number isn't re-cited here. What is measured: in the 12-image demo set below, only 1 of 12 OK results had a barcode in its `awb_source` (the rest leaned on the sorter overlay). The sorter overlay compensates heavily in _this_ dataset; a dataset without that overlay text would likely see a much lower OK rate from barcodes alone.
- **Ground truth is 38 images** — enough to catch the two systemic issues documented above, but not enough for statistically rigorous recall/precision claims.
- **Memory**: 11 worker processes measured ~7.1GB peak RSS in the Phase 3 load test. Reduce `WORKER_COUNT` on 8GB machines.
- **`OCR_PROVIDER=tesseract` and `SCENE_PROVIDER=ollama|clip` are not implemented** — they're reserved config slots for future work, not working toggles today (see Configuration table above). Setting them doesn't error, it just has no effect (OCR silently stays on rapidocr; scene falls back to heuristic with a warning).
- The `/api/images/{id}/annotated` endpoint (original image with detected boxes drawn) is a documented-optional stub, not implemented.

### Project Structure

```
case1-parcel-labels/
  README.md  AGENTS.md  .env.example  .gitignore
  docs/                       # architecture, data model, flag taxonomy, API spec, walkthrough
  backend/
    app/
      main.py                # FastAPI app, lifespan, SPA static serving
      config.py               # all tunables, env-overridable
      models.py / db.py       # SQLAlchemy models, SQLite (WAL mode)
      schemas.py / errors.py  # Pydantic response shapes, error taxonomy
      api/                    # batches.py images.py records.py export.py system.py
      services/               # queue.py (DB-backed queue) worker.py (process pool) storage.py
      pipeline/                # the extraction core - runs standalone via cli.py
        cli.py runner.py types.py preprocess.py quality.py label_detect.py
        barcode.py ocr.py overlay.py parse_fields.py scene.py decide.py
        couriers.yaml  providers/ocr_rapid.py
    tests/                    # pytest, 107 tests
  frontend/                   # React + TypeScript + Vite + TanStack Query
    src/{api,components,hooks,lib,routes}/
  eval/                       # ground_truth.csv, run_eval.py, reports/
  sample_data/                # demo_inputs/, demo_output.csv, demo_output.json, raw/ (gitignored, mostly)
  scripts/                    # run.sh/run.ps1 (production), dev.sh/dev.ps1 (hot reload)
```

Full architecture detail: `docs/architecture.md`.
