# Evaluation and Test Plan

Goal: prove, with numbers, that the system extracts correctly when it extracts and flags honestly when it cannot. The reviewers will run unseen images, so measure generalization, not only the sample set.

## 1. Ground truth (`eval/ground_truth.csv`)

Hand-annotate 40 to 60 images from the dataset (more is better; at least 5 per flag category that actually occurs). Columns:

| Column | Meaning |
| --- | --- |
| image_name | File name |
| truth_status | `OK` (clean readable label) or `FLAGGED` |
| truth_flag | One of the codes in `docs/flag_taxonomy.md` when FLAGGED. Use `LABEL_NOT_FOUND` only if the cause truly cannot be told by a human |
| truth_awb | The AWB as a human reads it (empty if not readable) |
| truth_weight_kg | Empty if not printed |
| truth_length_cm, truth_width_cm, truth_height_cm | Empty if not printed |
| notes | Anything odd (two labels, hand over label, etc.) |

Annotate before tuning thresholds, and keep a held-out part (about 30 percent) that you do not tune on. State this split in the report.

## 2. Metrics (`eval/run_eval.py`)

Primary (must be reported):

1. **Wrong-extraction rate** = OK rows whose AWB differs from truth / all OK rows. Target: 0 percent on the held-out set; any non-zero case is analyzed in the report.
2. **AWB recall on readable images** = correctly extracted OK AWBs / images where truth says OK.
3. **Flag rate** and **flag accuracy**: confusion matrix of predicted flag vs truth flag; per-flag precision and recall.
4. **Silent-miss rate**: truth FLAGGED but predicted OK (the dangerous direction). Report separately from wrong-extraction.
5. **Weight and dimensions accuracy** where truth exists: exact match after normalization (weight within 0.01 kg; dimensions within 0.5 cm), and the rate of non-empty but wrong values (should be ~0).
6. **Throughput**: images per minute, mean and p95 seconds per image, worker count, machine description.

Report format (`eval/reports/report_YYYYMMDD.md`): config used (providers, thresholds, pipeline version), table of metrics, confusion matrix, list of every wrong or silently missed case with image name and cause, and what changed since the previous report.

## 3. Robustness (approximate unseen data)

Create augmented copies of the evaluation images (script in `eval/augment.py`): rotate 90 and 180, downscale to 50 percent, Gaussian blur, brightness -30 percent and +30 percent, JPEG quality 40, add a small random crop. Re-run metrics and report the change. A good result is "recall drops, wrong-extraction stays near zero".

## 4. Test layers

| Layer | What | Tools |
| --- | --- | --- |
| Unit | `parse_fields` with 40+ weight/dimension string variants (g/kg/KG/Kgs, `0,5 kg`, `10 X 20 X 5`, `L:10 B:5 H:3`, mm/in, volumetric weight lines, OCR digit confusions) | pytest, parametrized |
| Unit | `decide` table-driven: one case per flag and per AWB acceptance row | pytest |
| Unit | Barcode decode on 3 to 5 small fixtures (clean, rotated, small, none) | pytest |
| Integration | API: empty upload, wrong type, corrupt file, oversized, unknown batch, finalize twice, cancel, export while processing | FastAPI TestClient |
| Integration | Worker: batch of 30 completes; poisoned image times out without stopping the batch; restart mid-batch resumes | pytest + temp dir |
| End to end | Browser flow with 100+ images; close and reopen tab; download CSV and compare to CLI output | manual script + checklist |

## 5. Edge-case checklist (Phase 6)

Bad input
- [ ] Empty upload (no files) shows a clear message, no crash
- [ ] `.txt`/`.pdf` renamed to `.jpg` is rejected with reason
- [ ] Truncated/corrupt JPEG and PNG become `ERROR / IMAGE_CORRUPT` or are rejected at upload, never crash
- [ ] 0-byte file, 1x1 px image, huge (12000 px) image, CMYK JPEG, grayscale PNG, PNG with alpha, EXIF-rotated phone photo
- [ ] File name with spaces, unicode, very long, duplicates, path-like names (`../../x.jpg`)
- [ ] Same image uploaded twice; two different images with the same AWB

Scale and robustness
- [ ] 300+ image batch finishes; UI stays responsive; memory stays bounded
- [ ] Close the tab during upload and during processing; reopen and see correct state
- [ ] Kill and restart the server mid-batch; processing resumes; no duplicate rows
- [ ] Two batches processed at once
- [ ] Cancel mid-batch; retry failed
- [ ] Delete batch frees disk space

Content cases (from the brief)
- [ ] No parcel in frame
- [ ] Multiple parcels
- [ ] Parcel partially visible
- [ ] Hand/object covering the label
- [ ] Label unreadable (blur, glare, dark)
- [ ] Label present with AWB but no weight/dimensions (still OK)
- [ ] Label with volumetric and dead weight both printed
- [ ] Rotated 90/180 labels
- [ ] Courier format not seen in the sample set (generic rules + flags, not a crash)

Outputs
- [ ] CSV opens in Excel and LibreOffice; special characters and commas in names handled; formula injection guarded; AWB README note present
- [ ] CSV row count equals accepted images; row order stable

## 6. Honesty items for the README

State: dataset size and categories, number annotated, held-out split, the metrics above with real numbers, the errors you found and what you changed, and what the free path cannot reliably distinguish (for example no parcel vs fully covered label without a scene model).
