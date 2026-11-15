# Flag Taxonomy and Decision Rules

Principle: **a wrong extraction is worse than an honest flag.** The decision module (`pipeline/decide.py`) is the only place that turns evidence into a verdict.

## 1. Outcome model

Each image ends with exactly one `status`:

| Status | Meaning |
| --- | --- |
| `OK` | A trustworthy AWB was read (see rules below). Weight and dimensions are filled only if present and trustworthy; missing ones are simply empty (the brief says "whichever are present"). |
| `FLAGGED` | A clean read is not possible. `primary_flag` says why. No AWB is written to the `awb` column. A best guess, if any, goes to `awb_suggestion` for human review only. |
| `ERROR` | The system failed (corrupt file, timeout, crash). Not an image-content problem. |

`primary_flag` is one code. `warnings` is a list of secondary codes that do not stop a row from being `OK`.

## 2. Flag codes

| Code | Status | Meaning | Main signals |
| --- | --- | --- | --- |
| `NO_PARCEL` | FLAGGED | No parcel in frame (empty belt/table) | Scene provider says parcel_count = 0; no barcode, almost no text, uniform scene |
| `MULTIPLE_PARCELS` | FLAGGED | More than one parcel, so the label read is ambiguous | 2 or more distinct AWB-like barcodes far apart; scene provider count >= 2; two separate label regions |
| `PARTIAL_PARCEL` | FLAGGED | Parcel or label cut off by the frame | Barcode/label bbox touches or is clipped by the image border; text lines truncated at border; scene provider says partial |
| `LABEL_BLOCKED` | FLAGGED | Label covered by a hand/object/tape | Barcode region detected but undecodable with occlusion evidence; scene provider says occluded |
| `LABEL_UNREADABLE` | FLAGGED | Label visible but cannot be read (blur, glare, low light, too small) | Label region found, quality metrics poor, decode and OCR both weak |
| `LABEL_NOT_FOUND` | FLAGGED | No label located and the cause cannot be determined without a scene model | No barcode, little text. Umbrella for no parcel, label facing away, or fully blocked |
| `LOW_CONFIDENCE_READ` | FLAGGED | An AWB candidate exists but evidence is too weak to trust | OCR-only AWB, confidence below threshold, or fails validation; candidate goes to `awb_suggestion` |
| `CONFLICTING_READS` | FLAGGED | Barcode and OCR give different AWBs, or two barcodes disagree | Mismatch after normalization |
| `AMBIGUOUS_AWB` | FLAGGED | Several AWB-like numbers on the label and none can be confirmed as the tracking number | Multiple candidates, no keyword proximity or pattern to separate them |
| `IMAGE_QUALITY_POOR` | FLAGGED | Image too blurry/dark/small to analyze at all | Blur and brightness below thresholds, or resolution too low |
| `IMAGE_CORRUPT` | ERROR | File cannot be opened as an image | Pillow fails |
| `PROCESSING_ERROR` | ERROR | Timeout or unexpected exception | Worker exception/timeout |

Warnings (never change `OK` into `FLAGGED` by themselves): `DUPLICATE_AWB`, `DUPLICATE_IMAGE`, `WEIGHT_UNCERTAIN`, `DIMENSIONS_UNCERTAIN`, `VOLUMETRIC_WEIGHT_IGNORED`, `ROTATED_IMAGE_FIXED`, `SCENE_PROVIDER_UNAVAILABLE`.

## 3. Priority order (when several flags could apply)

1. `IMAGE_CORRUPT` / `PROCESSING_ERROR` (ERROR)
2. `NO_PARCEL`
3. `MULTIPLE_PARCELS`
4. `PARTIAL_PARCEL`
5. `LABEL_BLOCKED`
6. `CONFLICTING_READS` / `AMBIGUOUS_AWB`
7. `LABEL_UNREADABLE` / `IMAGE_QUALITY_POOR`
8. `LOW_CONFIDENCE_READ`
9. `LABEL_NOT_FOUND`

Exception: if a barcode decoded to a valid, OCR-confirmed AWB and the scene evidence says only "partial" on an unrelated edge, prefer `OK` plus a warning. Evidence of a complete, valid read beats scene guesses.

## 4. AWB acceptance rules

**Phase 1 update:** there are three independent evidence channels, not two - `barcode`,
`ocr` (printed label text), and `overlay` (the warehouse sorter-camera text overlay
burned into the frame; see `docs/dataset-notes.md` section 2). The overlay is
structured key:value text and very reliable when present, but it is the sorter's
own sensor reading, not the courier's label, so it can be stale (AWB shown over an
empty belt) or implausible (0x0x0 dimensions, a weight far outside a parcel's
range) - every overlay value is plausibility-checked before being trusted, exactly
like a label-OCR value.

Candidate sources: `barcode`, `ocr`, `overlay`, and the two-source agreements
`both` (barcode+ocr), `barcode+overlay`, `ocr+overlay`.

| Evidence | Result |
| --- | --- |
| Barcode and overlay AWB agree | `OK`, confidence very high (about 0.98) |
| Barcode value matches a known/generic AWB pattern AND appears in OCR text | `OK`, confidence high (about 0.95) |
| Overlay AWB and label OCR AWB agree (no barcode decoded) | `OK`, confidence high (about 0.95) |
| Barcode value matches an AWB pattern, nothing else confirms it | `OK`, confidence medium (about 0.80), only if exactly one AWB-like barcode exists |
| Overlay AWB matches a known/generic pattern, a parcel is actually present, nothing else confirms it | `OK`, confidence medium (about 0.80) |
| Overlay reports an AWB (and/or weight/dimensions) but there is no other evidence of a parcel in frame | `NO_PARCEL` - the overlay is treated as stale, not as truth |
| Two or more different AWB-like barcodes | `MULTIPLE_PARCELS` (if far apart / scene agrees) or `AMBIGUOUS_AWB` |
| Barcode disagrees with overlay, or barcode disagrees with OCR | `CONFLICTING_READS`; put both values in `awb_suggestion` |
| OCR-only number near an AWB keyword, strict pattern, OCR confidence >= 0.90 (all digits) | `OK` only if the pattern has a checksum/prefix rule that validates; otherwise `LOW_CONFIDENCE_READ` |
| OCR-only, anything weaker | `LOW_CONFIDENCE_READ` with candidate in `awb_suggestion` |
| Nothing found | Scene-based flag, else `LABEL_NOT_FOUND` |

Overlay-specific plausibility: dimensions of 0x0x0 are discarded (`DIMENSIONS_UNCERTAIN`,
raw text kept for evidence); a weight outside `PLAUSIBLE_WEIGHT_KG` is discarded
(`WEIGHT_UNCERTAIN`) rather than trusted just because the sorter reported it. None
of the courier patterns found in Phase 0/1 have a checksum rule, so OCR-only AWBs
never reach `OK` by themselves in the current implementation - only via agreement
with a barcode or the overlay.

Thresholds live in `config.py` (override by env): `AWB_OCR_MIN_CONF`, `BLUR_MIN`, `BRIGHTNESS_MIN/MAX`, `MIN_IMAGE_SIDE`, `BORDER_MARGIN_PCT` (default 1.5 percent), `PLAUSIBLE_WEIGHT_KG` (0.01-50kg; capped below the architecture doc's original 100kg because this app is for parcels, not freight - see couriers.yaml notes), `PLAUSIBLE_DIM_CM`.

Courier patterns are generic and data-driven (`backend/app/pipeline/couriers.yaml`): name, regex, length rule, optional prefix list and checksum. Derive them from the real dataset in Phase 0; also keep a fallback generic rule (for example 8 to 20 alphanumeric characters, mostly digits) used only with the stricter evidence rows above.

## 5. Weight and dimension rules

- Extract only when the label text contains it. Missing is normal, not a flag.
- Weight needs a keyword and a unit; normalize to kg (g / 1000). Ignore text containing "vol" (volumetric) for `weight_kg` and add `VOLUMETRIC_WEIGHT_IGNORED`.
- Dimensions need three numbers separated by x/X/x/* or labelled L/B(W)/H; normalize to cm (mm / 10, inch * 2.54). Output length, width, height in the order printed.
- If the value fails plausibility or OCR confidence is low: leave empty and add `WEIGHT_UNCERTAIN` / `DIMENSIONS_UNCERTAIN` with the raw text in `weight_raw` / `dimensions_raw`.

## 6. Decision procedure (pseudocode)

```
decide(evidence):
  if evidence.load_error: return ERROR(IMAGE_CORRUPT)
  fields = parse_weight_dims(evidence)             # independent of AWB
  awb = resolve_awb(evidence)                      # per section 4 -> value, source, conf, or issue code

  if scene.parcel_count == 0:                      return FLAGGED(NO_PARCEL)
  if multiple_distinct_awb_barcodes or scene.parcel_count >= 2: return FLAGGED(MULTIPLE_PARCELS)
  if awb.ok and complete_read:                     return OK(awb, fields, warnings)
  if barcode_or_label_touches_border or scene.partial: return FLAGGED(PARTIAL_PARCEL)
  if scene.occluded or (barcode_region_found and not decoded and occlusion_hint): return FLAGGED(LABEL_BLOCKED)
  if awb.issue in (CONFLICTING_READS, AMBIGUOUS_AWB, LOW_CONFIDENCE_READ): return FLAGGED(awb.issue, suggestion)
  if quality_poor and no_text:                     return FLAGGED(IMAGE_QUALITY_POOR)
  if label_region_found:                            return FLAGGED(LABEL_UNREADABLE)
  return FLAGGED(LABEL_NOT_FOUND)
```

`flag_reason` is always a short plain sentence, for example "Barcode touches the right edge; label is cut off." Never leave a flag without a reason.

## 7. Examples

Updated at the end of Phase 6 with real image names and evidence from running the actual pipeline (`backend/app/pipeline/cli.py`) on the full 262-image `sample_data/raw` dataset (not invented). Every flag/status below is something that actually occurred in that run except where noted.

| Image | What it shows | Status / flag | Evidence collected |
| --- | --- | --- | --- |
| `10_jpeg.rf.XFK2Hy0xpa8FkMppr5ZH.jpeg` | Clean Delhivery poly-bag photo | **OK** | No barcode decoded; sorter overlay reports AWB `19109110324413`, confirmed by an independent OCR reading of the same number on the label (`awb_source=ocr+overlay`, confidence 0.95). |
| `No Shipment packet captured_png.rf.1VvRtdnwIQAHs1Q83pHV.png` | Empty conveyor belt, nothing in frame | **FLAGGED / NO_PARCEL** | No barcode, no label region found, no independent OCR text at all - only the overlay's own vocabulary (16 OCR lines, all explained by `Location/AWB_No/.../Time` field names). Overlay reports AWB `19108610815360`, correctly treated as stale and placed in `awb_suggestion`, never `awb`. |
| `No Shipment ccaptured_png.rf.7xveM0Q6aPacgoxworum.png` | Empty sloped platform/ramp, no parcel anywhere in frame | **FLAGGED / LOW_CONFIDENCE_READ** | This is the Phase 1 known-wrong case (was a false `OK`). `label_detect.py`'s brightness heuristic mis-identifies the bright platform surface as a label region (it's documented as allowed to do this); Phase 5 stopped trusting that signal alone for a confirmed read, but Phase 6 found that outright flagging it `NO_PARCEL` was too harsh at full-dataset scale for the 17/262 images where a label region genuinely is found - so this specific case lands on `LOW_CONFIDENCE_READ` with the overlay's AWB (`19108610815135`) as an honest, unverified `awb_suggestion` rather than either a confirmed `OK` or a flat "no parcel." Still correctly never asserts the AWB as fact - see the Phase 5/6 report for the full trade-off discussion. |
| `One more Ekart Format_png.rf.RjFc1ZG8LMmkelg5D2W8.png` | Sorter's own scanner reports "Barcode 2D: NoRead" (a disclosed sensor failure) plus an implausible 70kg weight on a small soft parcel | **FLAGGED / PARTIAL_PARCEL** | A non-overlay OCR/text line touches the frame border, so `text_truncated_at_border=True`. Weight `70.0kg` exceeds `PLAUSIBLE_WEIGHT_KG_MAX` (50kg) and is discarded (`WEIGHT_UNCERTAIN` warning) rather than output. No AWB confirmed - the only barcode present is a composite order string, not a numeric AWB. |
| `Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png` | Two distinct parcels in frame (a "Sparify" box and a "MYFITNESS" box) | **OK (known wrong - should be FLAGGED/MULTIPLE_PARCELS)** | No barcode decoded on either parcel, so the barcode-count check never fires. Phase 5 added `distinct_label_regions`/`distinct_ocr_awb_regions` specifically to catch this gap; neither fires here because the second parcel's only independent evidence is its brand-name text ("MYFITNE\"", "Explore"), not a second label-shaped region or a second AWB-shaped number. This is the one remaining documented wrong case - see Known Limitations in the README. |
| `corrupt_example_truncated.jpg` (deliberately created; no naturally-corrupt file exists in this dataset) | A JPEG file truncated mid-stream | **ERROR / IMAGE_CORRUPT** | `load_and_validate()` raises `ImageLoadError` ("image file is truncated..."); `process_image()` catches it and returns the error record without crashing the batch. |

**Flags never observed on a real image in this dataset** (implemented and covered by table-driven unit tests in `backend/tests/test_decide.py`, but no naturally-occurring example exists in `sample_data/raw` to cite here - not invented): `LABEL_BLOCKED`, `LABEL_UNREADABLE`, `LABEL_NOT_FOUND`, `CONFLICTING_READS`, `AMBIGUOUS_AWB`, `IMAGE_QUALITY_POOR`, `PROCESSING_ERROR`. The full 262-image run produced only four outcomes in practice: `OK` (180), `NO_PARCEL` (52), `LOW_CONFIDENCE_READ` (22), `PARTIAL_PARCEL` (8), `ERROR` (0 naturally-occurring).
