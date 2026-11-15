# API Specification (v1)

Base path: `/api`. JSON unless stated. Interactive docs: `/docs` (FastAPI). All times UTC ISO-8601.

## 1. Conventions

**Error shape (every non-2xx):**

```json
{ "error": { "code": "EMPTY_UPLOAD", "message": "No files were received. Choose one or more JPG or PNG images.", "details": {} } }
```

| HTTP | code examples |
| --- | --- |
| 400 | `EMPTY_UPLOAD`, `INVALID_REQUEST`, `BATCH_FINALIZED`, `TOO_MANY_FILES` |
| 404 | `BATCH_NOT_FOUND`, `IMAGE_NOT_FOUND` |
| 409 | `BATCH_NOT_READY` (e.g. export before any result) |
| 413 | `REQUEST_TOO_LARGE` |
| 422 | `VALIDATION_ERROR` |
| 500 | `INTERNAL_ERROR` (generic message only; details in server logs) |

**Pagination:** `?page=1&page_size=50` (max 200). Response includes `page`, `page_size`, `total`.

## 2. Endpoints

### System

`GET /api/health` -> `{ "status": "ok", "version": "1.0.0" }`

`GET /api/config` -> limits and capabilities so the UI can validate before upload:

```json
{
  "limits": { "max_file_mb": 15, "max_files_per_batch": 1000, "max_request_mb": 100, "allowed_types": ["image/jpeg", "image/png"] },
  "providers": { "ocr": "rapidocr", "scene": "heuristic", "scene_available": ["heuristic"] },
  "pipeline_version": "1.0.0"
}
```

### Batches

`POST /api/batches` body `{ "name": "Station 4 morning" }` (optional) -> `201`

```json
{ "batch_id": "b6f1...", "status": "created" }
```

`GET /api/batches?page=1&page_size=20` -> list of batch summaries (newest first).

`GET /api/batches/{batch_id}` -> progress and counts:

```json
{
  "batch_id": "b6f1...",
  "name": "Station 4 morning",
  "status": "processing",
  "finalized": true,
  "created_at": "2026-11-14T09:00:00Z",
  "total_images": 240,
  "rejected_count": 3,
  "processed": 118,
  "progress_pct": 49.2,
  "eta_seconds": 210,
  "counts": { "OK": 80, "FLAGGED": 36, "ERROR": 2 },
  "flag_counts": { "PARTIAL_PARCEL": 10, "NO_PARCEL": 8, "LABEL_BLOCKED": 6, "LABEL_UNREADABLE": 5, "MULTIPLE_PARCELS": 4, "LOW_CONFIDENCE_READ": 3 }
}
```

`POST /api/batches/{batch_id}/images` multipart, field `files` (repeatable). The client sends about 10 files per request, 2 to 3 requests in parallel. Returns `207`-style per-file outcomes (HTTP 200):

```json
{
  "accepted": [ { "image_id": "9f1c...", "name": "IMG_0412.jpg", "warnings": [] } ],
  "rejected": [ { "name": "notes.txt", "code": "NOT_AN_IMAGE", "message": "This file is not a valid JPG or PNG image." } ]
}
```

Rejection codes: `NOT_AN_IMAGE`, `CORRUPT_IMAGE`, `FILE_TOO_LARGE` (byte size over `MAX_FILE_MB`), `IMAGE_TOO_LARGE` (pixel count over `MAX_IMAGE_PIXELS` - a well-compressed file can be small in bytes yet still decode to an oversized bitmap, so this is checked separately from `FILE_TOO_LARGE`; Phase 6), `IMAGE_TOO_SMALL`, `UNSUPPORTED_TYPE`, `DUPLICATE_IN_BATCH` (accepted but warned instead, see below). Whole-request errors: `EMPTY_UPLOAD`, `REQUEST_TOO_LARGE`, `BATCH_FINALIZED`.

Accepted images enter the queue immediately. Exact duplicate files (same sha256 in the batch) are accepted with warning `DUPLICATE_IMAGE` and reuse the first result instead of reprocessing.

`POST /api/batches/{batch_id}/finalize` -> `{ "status": "processing" }` (no more files expected). Idempotent. If there are zero accepted images: `400 EMPTY_UPLOAD`.

`POST /api/batches/{batch_id}/cancel` -> stop claiming new images; running ones finish. `{ "status": "cancelled" }`.

`POST /api/batches/{batch_id}/retry-failed` -> requeue images in `ERROR`. `{ "requeued": 2 }`.

`DELETE /api/batches/{batch_id}` -> `204`; removes DB rows and files.

### Results

`GET /api/batches/{batch_id}/records?status=FLAGGED&flag=PARTIAL_PARCEL&q=123456&page=1&page_size=50&sort=upload_order`

-> `{ "items": [ResultRecord...], "page": 1, "page_size": 50, "total": 36 }` where `ResultRecord` is the JSON in `docs/data_model.md` section 2 plus `thumbnail_url`.

`GET /api/batches/{batch_id}/records/{image_id}` -> full record including `evidence` (barcodes, OCR lines with boxes, quality metrics, scene signals) and `image_url`.

### Images

`GET /api/images/{image_id}/thumbnail` -> `image/jpeg` (160 px). Cache headers allowed.
`GET /api/images/{image_id}/original` -> original bytes with correct content type.
`GET /api/images/{image_id}/annotated` -> optional: original with detected barcode/text boxes drawn (nice for review; build only if time permits).

### Export

`GET /api/batches/{batch_id}/export.csv?only=all|ok|flagged` -> `text/csv; charset=utf-8` attachment, streamed, columns per `docs/data_model.md` section 3. Works for partial results while processing (rows not yet processed have `status=PENDING` in CSV); the UI should only enable the main download when the batch is complete, with a "download partial results" option otherwise.

`GET /api/batches/{batch_id}/export-rejected.csv` -> rejected uploads with reasons (optional).

## 3. Client upload algorithm (frontend contract)

1. `GET /api/config` to read limits. Pre-check files client-side (type, size, count); show rejected ones before sending.
2. `POST /api/batches`.
3. Upload in groups of 10 files (max 40 MB per request), 2 to 3 groups in parallel, retrying a failed group up to 3 times with backoff. Show per-file status.
4. After all groups finish, `POST /finalize`.
5. Navigate to `/batches/{id}`; poll `GET /api/batches/{id}` every 2 seconds while status is `uploading` or `processing`; fetch records page by page; stop polling when complete.
6. Store `batch_id` in `localStorage` so the user can return; the batches list page also works.

## 4. Idempotency and safety

- `finalize`, `cancel`, `delete` are idempotent.
- Retrying an upload group may produce `DUPLICATE_IMAGE` warnings; this is expected.
- Never return filesystem paths. Image URLs use ids only.
