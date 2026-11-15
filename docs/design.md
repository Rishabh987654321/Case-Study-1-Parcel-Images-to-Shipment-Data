# UI / UX Design (Frontend)

Audience: a warehouse operator or supervisor, not a developer. Principles: obvious next step, never a frozen screen, plain language, honest about uncertainty. Polish is not scored; clarity and working flows are.

Stack: React + TypeScript + Vite, TanStack Query (polling and caching), Tailwind CSS. No heavy component library. Routes: `/` (upload), `/batches` (history), `/batches/:id` (results).

## 1. Screens

### 1.1 Upload (`/`)

```
+------------------------------------------------------------+
|  Parcel Label Reader                      [Past batches]   |
|                                                            |
|  +------------------------------------------------------+  |
|  |   Drag and drop parcel photos here                   |  |
|  |   or [Choose images]  [Choose a folder]              |  |
|  |   JPG or PNG, up to 15 MB each, up to 1000 images    |  |
|  +------------------------------------------------------+  |
|  Batch name (optional): [__________________]               |
|                                                            |
|  Selected: 240 images (3 skipped)  [Show skipped]          |
|  [Start processing]                                        |
+------------------------------------------------------------+
```

- Pre-check before sending: wrong type, too large, too many; list skipped files with reasons. Zero valid files disables the button with a message.
- After pressing start: per-file upload progress bar (overall "Uploaded 130 of 240"), failed chunks retry automatically; if retries fail, show "Retry failed uploads".
- When uploads finish: "Upload complete. Processing continues even if you close this page." then redirect to the batch page.

### 1.2 Batch results (`/batches/:id`)

```
+--------------------------------------------------------------------------+
| Station 4 morning     Processing 118/240 (49%)  about 3 min left        |
| [=======>              ]                                                  |
| OK 80 | Flagged 36 | Error 2        [Download all CSV v]                  |
+--------------------------------------------------------------------------+
| Filter: [All][OK][Flagged][Error]  Flag: [any v]  Search: [AWB or name ] |
+--------------------------------------------------------------------------+
| Photo | File          | AWB           | Weight | L x W x H  | Status     |
| [img] | IMG_0412.jpg  | 1234567890123 | 0.45kg | 20x15x10   | OK         |
| [img] | IMG_0587.jpg  | (not read)    |        |            | Partial    |
|       |               | Barcode touches the right edge; label is cut off. |
+--------------------------------------------------------------------------+
| < 1 2 3 ... >                                                            |
+--------------------------------------------------------------------------+
```

- Progress bar and counts update via polling every 2 seconds until complete; then stop polling and show "Done" (or "Done with N errors" plus a Retry failed button).
- Table is paginated (50 per page), thumbnails lazy-loaded.
- Rows for flagged items show the plain-language reason under the status badge. `awb_suggestion` is shown in grey italics as "Possible number (unverified): ..." and never in the AWB column.
- Download menu: All results, OK only, Flagged only, (Rejected uploads). While processing, the label reads "Download partial results".
- Buttons: Cancel (while processing), Retry failed (when errors exist), Delete batch (confirm dialog).

### 1.3 Row detail (drawer on row click)

- Large original image (click to zoom), prev/next arrows.
- Extracted fields with source and confidence ("AWB 1234567890123, read from barcode and text, high confidence").
- Status, flag and reason; warnings as small chips.
- "How it was read": detected barcodes (value, type), OCR lines (text, confidence). Collapsed by default.

### 1.4 Batches history (`/batches`)

Table of past batches: name, created time, total, OK/Flagged/Error counts, status, open and delete. Empty state: "No batches yet. Upload some photos to get started."

## 2. Status badges (colour is never the only signal; always show text)

| Status/flag | Label shown | Colour |
| --- | --- | --- |
| OK | Read | green |
| NO_PARCEL | No parcel in photo | grey |
| MULTIPLE_PARCELS | More than one parcel | amber |
| PARTIAL_PARCEL | Parcel partly out of frame | amber |
| LABEL_BLOCKED | Label covered | orange |
| LABEL_UNREADABLE | Label can't be read | orange |
| LABEL_NOT_FOUND | Label not found | grey |
| LOW_CONFIDENCE_READ | Unsure, needs a check | yellow |
| CONFLICTING_READS / AMBIGUOUS_AWB | Numbers don't agree / unclear | yellow |
| IMAGE_QUALITY_POOR | Photo too blurry or dark | orange |
| ERROR (IMAGE_CORRUPT, PROCESSING_ERROR) | Could not process | red |

## 3. Components

`UploadDropzone`, `FileChecklist` (skipped files), `UploadProgress`, `BatchHeader` (progress, counts, actions), `StatusFilterBar`, `ResultsTable`, `StatusBadge`, `ThumbCell`, `RecordDrawer`, `EvidencePanel`, `DownloadMenu`, `BatchesTable`, `ErrorBanner`, `EmptyState`, `ConfirmDialog`.

API client in `src/api/` with typed responses mirroring `docs/api.md`. Hooks: `useBatch(id)` (poll while active), `useRecords(id, filters, page)`, `useConfig()`.

## 4. States every screen must handle

Loading (skeleton or spinner), empty, error with retry, offline/server down ("Can't reach the server. Check that the app is running and try again."), stale (batch deleted elsewhere: "This batch no longer exists.").

## 5. Accessibility and usability

Keyboard-navigable table and drawer; focus trap in drawer; alt text for thumbnails (file name); contrast AA; no information by colour alone; works at 1280 px laptop width (mobile not required).

## 6. Error and message catalogue (plain language)

| Situation | Message |
| --- | --- |
| No files chosen | Choose one or more photos to start. |
| Wrong file type | "notes.txt" isn't a JPG or PNG image, so it was skipped. |
| File too large | "big.png" is larger than 15 MB and was skipped. |
| Too many files | You can upload up to 1000 images at once. The first 1000 were kept. |
| Corrupt image (server-side) | "photo_12.jpg" is damaged and couldn't be opened. |
| Server unreachable | Can't reach the server. Check that the app is running and try again. |
| Upload chunk failed after retries | Some files didn't upload. [Retry failed uploads] |
| Batch has no results yet | Processing has started. Results will appear here shortly. |
| Batch not found | This batch no longer exists. [Go to past batches] |
| Export with nothing to export | There are no results to download yet. |
| Unexpected error | Something went wrong on our side. Please try again. (Details are in the server log.) |

## 7. Demo script (for the 5-minute video)

1. Show the upload screen, drop 150+ images including a corrupt file and a text file; show skipped list.
2. Show progress while processing; close the tab and reopen from Past batches.
3. Filter Flagged; open one of each flag type and read the reason.
4. Download CSV; open it; point at AWB, flag, reason, suggestion columns.
5. Show one honest-flag example where the system refused to guess; mention the wrong-extraction rate from the evaluation report.
6. Mention limitations and what you would improve next.
