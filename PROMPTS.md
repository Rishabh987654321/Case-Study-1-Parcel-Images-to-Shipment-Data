# Paste-ready prompts for Antigravity (Case Study 1)

## Setup (do this once, by hand)

1. Create the repo folder `case1-parcel-labels/`.
2. Put `AGENTS.md` in the repo root.
3. Create a `docs/` folder and put these files in it: `architecture.md`, `flag_taxonomy.md`, `data_model.md`, `api.md`, `design.md`, `phases.md`, `evaluation.md`.
4. Download the dataset to `sample_data/raw/` (it is gitignored for now).
5. Open the folder in Antigravity, then paste the **Kickoff prompt**. After that, paste one **Phase prompt** at a time.

Tip: use a strong model for Phases 1, 3 and 5 (logic-heavy). Review each phase report yourself before saying go on. You must understand every file because the follow-up review includes a live change.

---

## Kickoff prompt (paste first)

```
You are my pair-programmer for a hiring take-home: Case Study 1, "Parcel Images to Shipment Data". A warehouse user bulk-uploads hundreds of parcel photos; the system reads each courier label and returns one record per image (AWB/tracking number, weight, dimensions) or an honest status flag, and the batch is downloadable as CSV. It must be free to run (no paid API keys), work in the background for large batches, and handle bad input without crashing.

Before writing any code:
1. Read AGENTS.md and every file in docs/ completely.
2. Reply with: (a) your understanding in at most 12 bullets (goal, architecture, flag taxonomy, non-negotiables), (b) any contradictions or gaps you found in the docs, (c) your questions and top 5 risks.
3. Then create only the repo scaffold from docs/architecture.md section 8: folders, empty modules with docstrings, .gitignore, .env.example, a README stub. No feature code yet.

We will work strictly phase by phase using docs/phases.md. Do not start Phase 0 until I say "go phase 0". At the end of every phase, stop and give a short report.
```

---

## Phase 0 prompt: dataset recon and tooling spike

```
go phase 0. Follow Phase 0 in docs/phases.md.
The dataset is in sample_data/raw/. First list what is there (counts, formats, sizes, resolutions) and look at a representative sample of images across the folders. Write docs/dataset-notes.md with only what you actually observe: couriers, barcode types, what each label prints (AWB, weight, dimensions, units and formats), and how often each problem appears (no parcel, multiple parcels, partial, blocked label, blur, rotation). List 10 example file names per category.
Then set up the Python venv and spike zxing-cpp and rapidocr-onnxruntime on 20 varied images with timings (scripts/spike.py). If OCR quality or installation is poor on this machine, test Tesseract and recommend one. Draft backend/app/pipeline/couriers.yaml from the AWB formats you really saw.
Do not build the API or UI. End with a short report and your OCR recommendation with numbers.
```

## Phase 1 prompt: extraction core + evaluation

```
go phase 1. Follow Phase 1 in docs/phases.md.
Build the pipeline in backend/app/pipeline/ exactly as in docs/architecture.md section 5 and apply the decision rules in docs/flag_taxonomy.md. Include the CLI (python -m app.pipeline.cli <folder> --out results.csv --json results.json).
Rules: barcode first, OCR to confirm; OCR-only AWBs are never accepted unless they pass the strict rule in the taxonomy; otherwise flag and put the candidate in awb_suggestion. Weight and dimensions only from label text with units, normalized to kg and cm. Every flagged row needs a plain-language flag_reason.
Create eval/ground_truth.csv with me: show me 60 image names that cover every category and I will annotate them (give me a CSV template to fill). Then implement eval/run_eval.py with the metrics in docs/evaluation.md and write the first report.
Add table-driven unit tests for parse_fields and decide. Iterate on the pipeline until the wrong-extraction rate is as low as possible, even if the flag rate rises. Report the numbers honestly, including every wrong or silently missed case.
```

## Phase 2 prompt: backend API and storage

```
go phase 2. Follow Phase 2 in docs/phases.md.
Implement the FastAPI app, SQLite models (docs/data_model.md) and all endpoints in docs/api.md except processing: batches, chunked image upload, finalize, records, thumbnails and image serving, config, health, delete. Validate uploads by content, enforce limits, generate thumbnails, detect duplicate sha256, and return per-file accepted/rejected results with clear reasons. Use the uniform error JSON; never leak stack traces.
Write API tests for: empty upload, a .txt renamed to .jpg, a corrupt JPEG, an oversized file, unknown batch id, finalize twice. Show me the Swagger page working and a curl example for each endpoint. Stop and report.
```

## Phase 3 prompt: background processing and CSV

```
go phase 3. Follow Phase 3 in docs/phases.md.
Add the queue service and worker pool (docs/architecture.md section 6): atomic claim with a single UPDATE, ProcessPoolExecutor, per-image timeout, error capture, stale-claim recovery on startup, cancel and retry-failed. Compute batch progress and an ETA. Add the duplicate-AWB post-check. Implement the streaming CSV export exactly as in docs/data_model.md section 3 (BOM, formula-injection guard, only=all|ok|flagged).
Prove it with tests: a 30-image batch completes; a poisoned image times out without stopping the batch; restarting the server mid-batch resumes without duplicate results. Also show that the CSV equals the CLI output for the same images. Stop and report.
```

## Phase 4 prompt: frontend

```
go phase 4. Follow Phase 4 in docs/phases.md and docs/design.md.
Build the React + TypeScript + Vite + Tailwind frontend with TanStack Query: upload page (pre-checks, chunked upload with retries and per-file status, finalize), batch results page (progress polling every 2 s, counts, filters, search, pagination, status badges with plain-language reasons, awb_suggestion shown as unverified), row detail drawer, download menu, batches history, localStorage for the last batch, and every error/empty state in docs/design.md section 6.
Wire the production build so FastAPI serves it on one port, and add scripts/run.ps1 and scripts/run.sh that set up the venv, install, build, and start. Test the full flow with 100+ images, closing and reopening the tab mid-processing. Stop and report with a short manual test checklist result.
```

## Phase 5 prompt: scene flags and generalization

```
go phase 5. Follow Phase 5 in docs/phases.md.
Improve NO_PARCEL, MULTIPLE_PARCELS, PARTIAL_PARCEL and LABEL_BLOCKED. First strengthen the deterministic signals (border-touching barcode or text, multiple distinct AWB-like barcodes far apart, barcode region found but not decodable). Then evaluate optional providers (ollama and/or clip) on eval/ground_truth.csv and keep one only if flag accuracy improves without increasing the wrong-extraction rate. The default must stay free and need no model download; fall back gracefully with a SCENE_PROVIDER_UNAVAILABLE warning.
Write eval/augment.py (rotate, downscale, blur, brightness, JPEG quality) and report the metric changes on augmented images. Show before/after per-flag precision and recall. Stop and report. Be honest about what the free path cannot distinguish.
```

## Phase 6 prompt: hardening

```
go phase 6. Follow Phase 6 and the checklist in docs/evaluation.md section 5.
Walk every checklist item, fix what fails, and mark each item done or listed as a known limitation with the reason. Run a 300+ image stress test (duplicate the dataset) and record total time, seconds per image (mean and p95) and peak memory. Check logging, temp-file cleanup and that delete-batch frees disk. Update docs/flag_taxonomy.md with real examples and file names. Stop and report.
```

## Phase 7 prompt: docs, samples, demo, submission

```
go phase 7. Follow Phase 7 in docs/phases.md.
Write the Case 1 README: run locally in under 15 minutes (Windows and macOS/Linux), the free path, approach and why, flag taxonomy summary, evaluation results with real numbers, what I would improve with more time, and honest known limitations (include the Excel long-AWB note). Prepare sample_data/ with a small subset of inputs and the outputs the system produced. Write docs/walkthrough.md mapping "if asked to change X, edit file Y" for: add a flag, change a threshold, add a CSV column, add a courier pattern, change the OCR engine. Verify a clean clone runs using only the README. Give me a demo script for a 5-minute video and a submission checklist (no secrets, repo shared with gourav.rathi@prozo.com).
```

---

## Utility prompts

**Review before moving on**

```
Before we proceed, review what you just built against AGENTS.md and the phase acceptance criteria. List anything that does not meet them, any shortcut you took, and any place where a wrong extraction could slip through. Do not fix anything yet; just report.
```

**When extraction is wrong**

```
For these images: <names>, show the evidence the pipeline collected (barcodes, OCR lines with confidence, quality metrics, scene signals) and why decide.py produced its verdict. Propose the smallest change that fixes the case without increasing the wrong-extraction rate, and re-run the evaluation to prove it.
```

**Prepare me for the live review**

```
Quiz me on this codebase. Ask one question at a time about how a part works or where to change something (for example add a new flag or change a threshold). After my answer, correct me and point to the exact file and function.
```
