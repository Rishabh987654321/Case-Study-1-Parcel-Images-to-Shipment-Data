# Demo Script (5-minute screen recording)

**Before recording** (not on camera): start the app (`./scripts/run.sh`), then upload and finalize `sample_data/demo_inputs/` (12 curated images — one per flag category, plus one deliberately-corrupt file) as its own batch and let it finish processing. Note its URL (`/batches/<id>`) so you can jump straight to it for Beats 3–4. Processing 262 live on camera would take ~3-4 minutes by itself (measured: 203.8s for the full dataset at `WORKER_COUNT=11`) — too slow for a 5-minute recording, so the live upload in Beat 1 uses a smaller slice instead.

Also create one throwaway bad file to drop in during Beat 1:
```bash
echo "not an image" > ~/Desktop/notes.txt
```

## Beat 1 — Live upload, 0:00–1:15

1. Open http://localhost:8000 (Upload page, or click "Upload" in the nav).
2. Drag in **30-40 images** from `sample_data/raw` plus the `notes.txt` file. **Say:** "I'm dropping real warehouse photos plus one obviously-wrong file."
3. Point at the pre-upload summary ("N images ready to upload, 1 rejected") and the rejection message in the checklist: `"notes.txt" isn't a JPG or PNG image, so it was skipped.` — **say:** "That's caught client-side, before anything is even sent to the server."
4. Click Upload. Narrate the per-file checklist icons (⏳/🔄/✅) and the overall progress bar for a few seconds, then let it auto-navigate to the batch page.

## Beat 2 — Processing, close tab, reopen, 1:15–2:00

1. On the batch page, point at the live progress bar, the ETA, and the OK/Flagged/Error counts updating every 2 seconds.
2. **Close the browser tab entirely** while it's still processing. **Say:** "Processing keeps running on the server even if I walk away — it's not tied to this browser tab."
3. Reopen http://localhost:8000. It lands on History (or shows a "Continue with last batch" link) — click through back to the same batch. **Say:** "Still exactly where I left it."

## Beat 3 — Switch to the pre-processed batch, filter, inspect, 2:00–3:30

1. Navigate to the pre-processed `demo_inputs` batch you prepared earlier (History page, or paste its URL). **Say:** "This one finished earlier so we're not waiting on 11 workers live — same system, same output."
2. Click the **Flagged** tab, point at the count and the flag-code dropdown (`NO_PARCEL`, `PARTIAL_PARCEL`).
3. Click a flagged row to open the drawer. Read the plain-language `flag_reason` out loud (e.g. "No parcel, barcode, or label text found; the frame appears empty."). Expand "How it was read" and point at the raw OCR lines / barcode list behind that verdict.
4. Click Next a couple of times to step through more rows without closing the drawer. Close it.
5. Type an AWB fragment into search (e.g. `19109`) and show the table filtering live.

## Beat 4 — The honest-flag moment, 3:30–4:15

1. Filter to **OK**, open a row with a clean AWB, point at the AWB value + source + confidence text in the drawer (e.g. "19109110324413 — from ocr+overlay, confidence 0.95").
2. Now open the row for **`Multiple shipment packets in single sorter images_png...`** (included in `demo_inputs` on purpose) — one of exactly two documented wrong cases in the whole evaluation. **Say, plainly:** "This one is actually a known mistake — ground truth says two parcels in frame, the system returns OK with one AWB. We measured a 6.9% wrong-extraction rate on our 38-image labeled set, and this is one of the two wrong rows behind that number. I'd rather show you the real number and the real failure than hide it." This is the most important 20 seconds of the recording — it backs "abstain over guess" with an honest measurement, not just a slogan.

## Beat 5 — Export and wrap-up, 4:15–5:00

1. Click **Download All (CSV)**, open it in a spreadsheet. Point at `awb`, `primary_flag`, `flag_reason`, and `awb_suggestion` side by side on one flagged row — **say:** "The suggestion column is never auto-trusted into `awb` — it's there for a human to check."
2. One sentence on limitations: "Without a scene-recognition model we can't always tell 'no parcel' apart from 'label just wasn't found,' and that's the single biggest thing I'd add next, along with more ground truth than 38 images."
3. End on the History page showing both batches from this recording, to show batches persist across sessions.

## If something goes wrong live

- If the live-uploaded batch (Beat 1-2) is still processing when you reach Beat 3, that's fine — switch to the pre-processed `demo_inputs` batch as written above; don't wait on camera.
- If asked on the spot to change something, `docs/walkthrough.md` has the exact file/function for the most likely requests.
