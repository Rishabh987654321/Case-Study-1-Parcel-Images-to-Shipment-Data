# Phases: Case Study 1 (Parcel Images to Shipment Data)

Work one phase at a time. Each phase ends with a short report (what was built, how to verify, what is deferred, risks). Do not start the next phase until told.

Suggested time budget: about 1.5 to 2 days of focused work for the whole case, because Cases 2 and 3 also need time before the deadline. If a phase overruns, cut scope (see "Cut list" at the end), not the evaluation or honesty.

Why this order: the biggest risk is extraction accuracy, so the pipeline is built and measured first (as a CLI), and the web app is wrapped around a pipeline that is already known to work.

---

## Phase 0: Dataset recon and tooling spike (about 1.5 h)

**Goal.** Learn what the real images look like and prove the tools install and run on this machine.

**Tasks**

1. Put the downloaded dataset in `sample_data/raw/` (keep the original folder structure; do not commit the whole thing if it is large, commit a small subset later).
2. Write `docs/dataset-notes.md`: image count, resolution range, file types, couriers seen, barcode types (Code128, QR, etc.), what the label prints (AWB, weight, dimensions, which units/formats), how often each problem occurs (no parcel, multiple, partial, blocked, blurry), rotations, lighting. Include 10 representative file names per category. State only what you actually observed.
3. Create the repo scaffold from `docs/architecture.md` section 8 (folders, `.gitignore`, `.env.example`, empty modules).
4. Spike: install `zxing-cpp`, `rapidocr-onnxruntime`, Pillow, OpenCV (headless), NumPy in a venv. Run barcode decode and OCR on 20 varied images. Print timing and results. If OCR is poor or install fails on Windows, test Tesseract and decide. Record the decision and numbers in `docs/dataset-notes.md`.
5. Draft `couriers.yaml` from observed AWB formats (regex, length, prefixes).

**Deliverables.** `dataset-notes.md`, working venv + `requirements.txt` (pinned), a `scripts/spike.py` that prints results for 20 images.

**Acceptance.** Barcode decode and OCR run on the target machine; dataset notes list real categories with example file names; chosen OCR engine justified with timings.

---

## Phase 1: Extraction core as a CLI, plus ground truth (about 4 h)

**Goal.** An accurate, honest pipeline that works without any web code.

**Tasks**

1. Implement `pipeline/` modules per `docs/architecture.md` section 5: preprocess, quality, barcode (with retry cascade), ocr (interface + RapidOCR provider), parse_fields (AWB candidates, weight, dimensions, unit normalization, plausibility), decide (per `docs/flag_taxonomy.md`), runner, types.
2. CLI: `python -m app.pipeline.cli <folder> --out results.csv --json results.json` prints a summary (counts by status and flag, timing).
3. Create `eval/ground_truth.csv` by annotating 40 to 60 images from the dataset (see `docs/evaluation.md`). Cover every flag category.
4. `eval/run_eval.py` computes the metrics in `docs/evaluation.md` and writes `eval/reports/report_<date>.md`.
5. Unit tests for parse_fields (many weight/dimension string variants), decide (table-driven, one case per flag), barcode on 3 to 5 tiny fixtures.
6. Iterate until the wrong-extraction rate is as close to zero as achievable. Prefer raising flag rate over letting a wrong AWB through.

**Acceptance**

- CLI runs on the whole dataset without crashing; corrupt files give `ERROR` rows.
- Evaluation report exists with: wrong-extraction rate among OK rows, AWB recall on the readable set, flag confusion matrix.
- Every flagged row has a non-empty `flag_reason`.
- Unit tests pass.

---

## Phase 2: Backend API, storage and database (about 3 h)

**Goal.** Persistent batches and uploads with strict validation.

**Tasks**

1. FastAPI app, config from env, SQLite models per `docs/data_model.md`, startup migrations (create tables).
2. Endpoints per `docs/api.md`: create batch, upload images (chunked), finalize, get batch, list records (filter, pagination), get record, image/thumbnail serving, list batches, delete batch, health, config.
3. Upload validation: content-based image check, size and count limits, empty upload, duplicate hash (warning), per-file accept/reject report. Thumbnail generation.
4. Uniform error JSON; no stack traces to clients.
5. API tests with FastAPI `TestClient` (empty upload, wrong type, corrupt file, oversized, unknown batch id).

**Acceptance.** Swagger at `/docs` works; uploading 20 mixed files (including a corrupt one and a .txt renamed to .jpg) returns per-file accepted/rejected with clear reasons; data survives a server restart.

---

## Phase 3: Background processing, progress and CSV export (about 3 h)

**Goal.** Large batches never block; progress is visible; results survive closing the tab.

**Tasks**

1. Queue service and worker pool per `docs/architecture.md` section 6: atomic claim, `ProcessPoolExecutor`, per-image timeout, error capture, stale-claim recovery on startup, cancel, retry-failed.
2. Batch progress computed from DB (processed, total, counts by status/flag, ETA estimate).
3. Duplicate AWB post-check across the batch.
4. CSV export streaming per `docs/data_model.md` section 3 with `only` filter, BOM, formula-injection guard.
5. Tests: a batch of 30 images completes; kill and restart the server mid-batch and verify it resumes; one poisoned image (timeout/exception) does not stop the batch.

**Acceptance.** Uploading 100 images returns immediately; polling shows increasing progress; CSV matches the CLI output for the same images; restart-recovery test passes.

---

## Phase 4: Frontend (about 4 h)

**Goal.** A non-technical user can upload, watch progress, review, and download.

**Tasks** (see `docs/design.md`)

1. Upload page: drag-and-drop or folder/multi-select, client-side pre-check (type, size, count), chunked upload with per-file status and retry, clear messages.
2. Batch page: progress bar, counts by status, live table (thumbnail, name, AWB, weight, dimensions, status badge, reason), filters (All / OK / Flagged / Error, by flag), search by AWB or name, pagination.
3. Row detail drawer: large image, extracted fields, evidence (OCR text, barcodes), reason, warnings.
4. Download buttons: all, OK only, flagged only.
5. Batches history page (come back later), remembers last batch in localStorage.
6. Error and empty states everywhere (server down, empty upload, zero results).

**Acceptance.** Full flow works in the browser with 100+ images; refreshing or closing the tab and returning shows the same batch; every error case in `docs/design.md` section 6 shows a readable message.

---

## Phase 5: Scene flags and generalization (about 3 h)

**Goal.** Improve the flags that need judgment: no parcel, multiple parcels, partial parcel, blocked label.

**Tasks**

1. Strengthen deterministic signals: border-touching barcode/text, multiple distinct AWB barcodes with spatial separation, label-like region detection, "barcode region found but not decodable".
2. Evaluate optional providers (`ollama` and/or `clip`) on the ground-truth set. Keep one only if it measurably improves flag accuracy without raising the wrong-extraction rate. Default stays free and download-free (`heuristic`).
3. Make the provider selectable by env, with graceful fallback and a `SCENE_PROVIDER_UNAVAILABLE` warning.
4. Robustness test: run the evaluation on augmented copies of the dataset (rotate 90/180, downscale 50 percent, blur, brightness change, JPEG quality 40) to approximate unseen images. Record the drop in the report.

**Acceptance.** Evaluation report shows per-flag precision/recall before and after; the wrong-extraction rate did not get worse; README section drafted on what the free path can and cannot distinguish.

---

## Phase 6: Hardening and edge cases (about 2 h)

**Tasks**

1. Walk the checklist in `docs/evaluation.md` section 5 (bad input, big batch, odd images, concurrency, restart).
2. Stress test with 300+ images (duplicate the dataset); record time and memory.
3. Fix logging (structured, no PII), cleanup of temp files, delete-batch frees disk.
4. Final pass on `docs/flag_taxonomy.md` with real examples and image names.

**Acceptance.** Every item in the checklist is ticked or listed as a known limitation with the reason.

---

## Phase 7: Docs, samples, demo and submission (about 2 h)

**Tasks**

1. README for Case 1: run locally in under 15 minutes (Windows and macOS/Linux commands), free path, approach and why, flag taxonomy summary, evaluation results (real numbers), what you would improve with more time, known limitations (be candid).
2. `sample_data/`: a small subset of input images and the outputs the system produced (CSV + JSON).
3. Run scripts (`run.ps1` / `run.sh`) tested from a clean clone in a fresh folder.
4. 5-minute demo video: upload, progress, flagged examples, CSV, one failure case, one thing you would improve.
5. Review-readiness: be able to explain each module and make a small live change (for example add a new flag, change a threshold, add a CSV column). Write a one-page `docs/walkthrough.md` mapping "if asked to change X, edit file Y".
6. Share the repo with gourav.rathi@prozo.com; confirm no secrets are committed.

**Acceptance.** A clean clone runs following only the README; the demo video is under 5 minutes.

---

## Cut list (if time runs short, drop in this order)

1. `clip` / `ollama` providers (keep `heuristic`).
2. Batches history page (keep last-batch memory).
3. Retry-failed and cancel buttons (keep the API).
4. Row detail drawer evidence panel (keep the image and reason).

Never cut: the evaluation report, honest flags, chunked background processing, input validation, the README limitations section.
