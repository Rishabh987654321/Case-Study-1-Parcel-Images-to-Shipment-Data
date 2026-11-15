# Data Model, Result Schema and CSV Spec

SQLite (WAL mode), accessed through SQLAlchemy 2.0. Times are UTC ISO-8601. IDs are UUID4 strings.

## 1. Tables

### `batches`
| Column | Type | Notes |
| --- | --- | --- |
| id | text PK | UUID |
| name | text null | Optional label from the user |
| status | text | `created, uploading, processing, completed, completed_with_errors, cancelled` (derived values are recomputed on read) |
| finalized | bool | True after `/finalize` |
| total_images | int | Accepted images |
| rejected_count | int | Files rejected at upload |
| created_at, started_at, finished_at, last_activity_at | datetime | |

### `images`
| Column | Type | Notes |
| --- | --- | --- |
| id | text PK | UUID |
| batch_id | text FK | |
| original_name | text | Display only, never used as a path |
| stored_path | text | `data/uploads/{batch_id}/{id}.{ext}` |
| thumb_path | text | 160 px thumbnail |
| sha256 | text | For duplicate detection |
| width, height, size_bytes | int | |
| state | text | `queued, processing, done, error` |
| attempts | int | Retries |
| claimed_at | datetime null | For stale-claim recovery |
| created_at | datetime | |

### `results` (one row per image)
| Column | Type | Notes |
| --- | --- | --- |
| image_id | text PK/FK | |
| status | text | `OK, FLAGGED, ERROR` |
| primary_flag | text null | See `docs/flag_taxonomy.md` |
| flag_reason | text null | Human sentence |
| warnings | json | List of warning codes |
| awb | text null | Only when trusted |
| awb_source | text null | `barcode, ocr, overlay, both` (both = barcode+ocr), or a `+`-joined combination such as `barcode+overlay`, `ocr+overlay` (Phase 1 added the sorter-overlay channel; see docs/dataset-notes.md section 2) |
| awb_confidence | real null | 0 to 1 |
| awb_suggestion | text null | Candidate for review, never trusted |
| weight_kg | real null | |
| weight_raw | text null | Raw text seen on label |
| length_cm, width_cm, height_cm | real null | |
| dimensions_raw | text null | |
| courier | text null | If a known pattern matched; else null |
| confidence | real | Overall, 0 to 1 |
| evidence | json | Barcodes (value, type, bbox), OCR lines (text, conf, bbox), quality metrics, scene signals |
| pipeline_version | text | e.g. `1.0.0` plus provider names |
| processing_ms | int | |
| processed_at | datetime | |

Indexes: `images(batch_id, state)`, `results(status)`, `results(awb)`, `images(sha256)`.

## 2. Result JSON (API shape)

```json
{
  "image_id": "9f1c...",
  "image_name": "IMG_0412.jpg",
  "status": "OK",
  "primary_flag": null,
  "flag_reason": null,
  "warnings": ["VOLUMETRIC_WEIGHT_IGNORED"],
  "awb": "1234567890123",
  "awb_source": "both",
  "awb_confidence": 0.95,
  "awb_suggestion": null,
  "weight_kg": 0.45,
  "weight_raw": "Wt: 450 g",
  "dimensions_cm": {"length": 20, "width": 15, "height": 10},
  "dimensions_raw": "20x15x10 cm",
  "courier": "Delhivery",
  "confidence": 0.93,
  "processing_ms": 2310
}
```

A flagged example:

```json
{
  "image_id": "a31b...",
  "image_name": "IMG_0587.jpg",
  "status": "FLAGGED",
  "primary_flag": "PARTIAL_PARCEL",
  "flag_reason": "Barcode touches the right edge; label is cut off.",
  "warnings": [],
  "awb": null,
  "awb_suggestion": "1234567890",
  "weight_kg": null,
  "dimensions_cm": null,
  "confidence": 0.2
}
```

## 3. CSV export spec

File name: `parcel_results_{batch_id}_{YYYYMMDD-HHMM}.csv`. UTF-8 with BOM. One header row. One row per **accepted** image (rejected uploads are listed in a separate `rejected_files.csv` option or in the UI, not mixed in). Row order = upload order.

| # | Column | Notes |
| --- | --- | --- |
| 1 | image_name | Original file name |
| 2 | status | OK / FLAGGED / ERROR / PENDING (not yet processed; display-only, never stored) |
| 3 | primary_flag | Empty for OK |
| 4 | flag_reason | Short sentence |
| 5 | awb | Empty unless trusted |
| 6 | awb_suggestion | Review-only candidate |
| 7 | awb_source | barcode / ocr / overlay / both / barcode+overlay / ocr+overlay |
| 8 | awb_confidence | 0 to 1, 2 decimals |
| 9 | weight_kg | Number, dot decimal, empty if absent |
| 10 | weight_raw | |
| 11 | length_cm | |
| 12 | width_cm | |
| 13 | height_cm | |
| 14 | dimensions_raw | |
| 15 | warnings | Semicolon-separated codes |
| 16 | processed_at | UTC ISO-8601 |
| 17 | pipeline_version | e.g. `1.0.0` |
| 18 | image_id | |

Phase 3 note: this column set/order superseded an earlier draft (which had `weight_kg` right
after `awb`, plus `courier`, `confidence`, and `batch_id` columns instead of `awb_confidence`,
`pipeline_version`, `image_id`). Dropped `courier` and overall `confidence` because `awb_confidence`
already conveys read trust and courier is derivable from the AWB pattern; dropped `batch_id` because
the export is already scoped to one batch via the URL. Added `pipeline_version` and `image_id` for
reproducibility and precise cross-referencing back to a specific image/record.

Rules:
- Quote every text field; escape quotes; neutralize formula injection (leading `=`, `+`, `-`, `@` gets a leading `'`).
- AWB is a text value. Long numeric AWBs may turn into scientific notation if opened directly in Excel; the README must explain "Data, From Text/CSV, set AWB column to Text".
- Supports `?only=ok`, `?only=flagged` (see `docs/api.md`).
- Stream the file (do not build it all in memory).

## 4. Config and env (`.env.example`)

```
MAX_FILE_MB=15
MAX_FILES_PER_BATCH=1000
MAX_REQUEST_MB=100
MIN_IMAGE_SIDE=300
MAX_IMAGE_PIXELS=144000000   # 12000x12000, PIL decompression-bomb guard
WORKER_COUNT=            # blank = cpu_count - 1
IMAGE_TIMEOUT_S=60
WORKING_MAX_SIDE=2000
THUMBNAIL_MAX_SIDE=160
OCR_PROVIDER=rapidocr    # rapidocr | tesseract
SCENE_PROVIDER=heuristic # none | heuristic | ollama | clip
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=
DATA_DIR=data
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173   # comma-separated if more than one (Phase 2)
```

Phase 2 note: `MAX_REQUEST_MB` is enforced by a middleware that checks the `Content-Length` header
before the body is parsed (so a huge upload is rejected immediately, not after reading it into
memory). This relies on the client sending `Content-Length`, which every browser and HTTP client
library does for multipart uploads; a chunked request with no `Content-Length` would skip this
specific check and fall through to the normal per-file validation instead.
