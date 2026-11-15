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

Candidate sources: `barcode`, `ocr`, `both` (barcode value found in OCR text after normalization).

| Evidence | Result |
| --- | --- |
| Barcode value matches a known/generic AWB pattern AND appears in OCR text | `OK`, confidence high (about 0.95) |
| Barcode value matches an AWB pattern, OCR did not confirm (small text, glare) | `OK`, confidence medium (about 0.80), only if exactly one AWB-like barcode exists |
| Two or more different AWB-like barcodes | `MULTIPLE_PARCELS` (if far apart / scene agrees) or `AMBIGUOUS_AWB` |
| Barcode and OCR give different values | `CONFLICTING_READS`; put both in `awb_suggestion` |
| OCR-only number near an AWB keyword, strict pattern, OCR confidence >= 0.90 (all digits) | `OK` only if the pattern has a checksum/prefix rule that validates; otherwise `LOW_CONFIDENCE_READ` |
| OCR-only, anything weaker | `LOW_CONFIDENCE_READ` with candidate in `awb_suggestion` |
| Nothing found | Scene-based flag, else `LABEL_NOT_FOUND` |

Thresholds live in `config.py` (override by env): `AWB_OCR_MIN_CONF`, `BLUR_MIN`, `BRIGHTNESS_MIN/MAX`, `MIN_IMAGE_SIDE`, `BORDER_MARGIN_PCT` (default 1.5 percent), `PLAUSIBLE_WEIGHT_KG`, `PLAUSIBLE_DIM_CM`.

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

| Situation | Status | Flag / warning | awb column |
| --- | --- | --- | --- |
| Clear label, barcode decodes, number also in OCR, weight "0.45 kg" | OK | none | filled |
| Clear label, no weight/dimensions printed | OK | none | filled, others empty |
| Barcode decodes but label printed small, OCR missed it | OK (medium) | none | filled |
| Hand covers half the label, barcode not decodable, OCR sees fragments | FLAGGED | LABEL_BLOCKED or LABEL_UNREADABLE | empty |
| Two parcels with two different AWB barcodes | FLAGGED | MULTIPLE_PARCELS | empty |
| Empty belt | FLAGGED | NO_PARCEL (or LABEL_NOT_FOUND without scene provider) | empty |
| Label cut at the frame edge | FLAGGED | PARTIAL_PARCEL | empty |
| OCR reads a 12-digit number but no barcode | FLAGGED | LOW_CONFIDENCE_READ | empty; value in `awb_suggestion` |
| Truncated JPEG | ERROR | IMAGE_CORRUPT | empty |

Update this file (with real examples and image names) at the end of Phase 0 and Phase 6.
