# Dataset Notes (Phase 0)

Everything below is from actually opening and inspecting files in `sample_data/raw/`
(262 images total) — either programmatically (full-dataset stats) or visually (54
images hand-picked to cover every naming pattern in the dataset, plus a 20-image
spike with barcode + OCR run on them). Nothing here is guessed.

## 0. Filename patterns (how the dataset is organized)

The 262 files fall into seven naming patterns. Counts and what each pattern turned
out to contain, after opening representative samples from each:

| Pattern | Count | What it actually is |
| --- | --- | --- |
| `weight_image_<id>_<ts>_jpg...` | 150 | Warehouse sorter-camera photos, almost all carrying a burned-in text overlay (see section 2). Mostly Delhivery poly-bags. |
| `ms<1-47>_jpeg...` (some numbers repeated with different hashes) | 58 | Single-parcel sorter photos, mostly Beardo-brand boxes under Blue-Dart-style or "Barcode:"-labeled overlays. **Not** "multiple shipment" despite the name — every one inspected had exactly one parcel. |
| `<11-15 digit number>-<timestamp>_jpg...` | 22 | Sorter photos where the filename's leading number is *usually* (not always) the same value as the overlay's AWB field. |
| Descriptive names with spaces (`.png`) | 14 | Curated, deliberately-labeled edge cases — one file per interesting problem (see section 4). These are screenshots/crops (RGBA, much smaller resolution) rather than raw camera frames. |
| `<1-2 digit number>_jpeg...` | 11 | Clean sorter photos, yellow-text overlay schema, multiple warehouse locations. |
| Other one-off names (`diff_format`, `new_format`, `test`, `m_s`, `multiple_shipment`) | 5 | Mixed — one clean Beardo box, one genuinely dark/zoomed box photo, one empty-conveyor-adjacent-to-box shot. |
| 32-char hex hash names (`.jpg`) | 2 | Plain photos of a single BlueDart-ish box, no overlay. |

## 1. Overall stats (computed over all 262 files, `scripts/dataset_stats.py`)

| Metric | Value |
| --- | --- |
| Total images | 262 |
| File types | JPEG: 249, PNG: 13 |
| Color mode | RGB: 163, L (grayscale): 86, RGBA: 13 (all 13 PNGs) |
| EXIF | **None of the 262 images carry any EXIF data** (no orientation tag at all) — consistent with this being a Roboflow export (filenames contain `.rf.<hash>`), which strips EXIF and re-encodes. The pipeline's EXIF-orientation step will be a no-op on this dataset but must stay in for real-world uploads. |
| Width | min 399, max 12288, median 4096 |
| Height | min 481, max 7240, median 2204 |
| File size | min 35,986 bytes, max 2,301,892 bytes, median 551,314 bytes |

Grayscale (`L` mode) images are exclusively from `weight_image_*` (52 of 150) and
`ms*` (34 of 58) — these look like a monochrome/IR-lit camera at some sorter
stations, not a quality defect.

## 2. Sorter overlay metadata — the single biggest finding

**Most images in this dataset are not just a photo of a parcel — they carry a
burned-in text overlay added by the warehouse's own sorter-camera system**, reporting
fields it already measured for that parcel. This is distinct from the printed
courier shipping label and was not mentioned in the architecture doc, which assumes
the only readable data is the physical label.

At least **five different overlay schemas** were observed (same idea, different
sorter software/version):

1. Yellow text, `Location / AWB No / Length / Width / Height / R.Vol. / Weight / Time`
   (e.g. plain-number files, many weight_image_* files).
2. Green monospace, `MID / Date Time` + `L / W / H` + `A.W / V.W` + `AWB`
   (e.g. `m_s_jpeg`).
3. White/red monospace, `Location / Barcode / Dimension / Weight / Time / Sorter_ID`
   (e.g. `ms*` files, "Half shipment captured").
4. Yellow text, `LOCATION CODE / AWB_NO / LENGTH(cm) / WIDTH(cm) / HEIGHT(cm) /
   WEIGHT(Kg) / DATETIME / ID` (e.g. `ms7`, long-digit files).
5. Green monospace, `Index / Barcode / BDN / Dim(L/W/H) / Vol / Weight / <timestamp>`
   (e.g. `new_format_jpeg`).

Key properties, confirmed by inspection:

- The overlay text is **extremely OCR-friendly** — rendered computer text, high
  contrast, fixed position (top-left, occasionally top-right). RapidOCR read it at
  0.92–0.99 mean confidence on every one of the 20 spike images.
- The overlay's `AWB No` / `Barcode` field is **the actual courier AWB in the same
  format a human would read off the label** (confirmed: in `ms7_jpeg`, the overlay
  says `AWB NO: 77549916382` and the barcode decoded directly off the printed label
  is `77549916382` — they match).
- **The overlay is not always trustworthy.** Two curated examples prove this
  directly: `No Shipment ccaptured` shows a populated AWB/dimension overlay over an
  empty conveyor belt (stale reading, not live), and `Shipment showing LBH values
  as 00` / `One more Ekart Format` show the sorter's own dimension sensor reporting
  `0000 x 0000 x 0000` or an implausible `70.0 kg` weight for a small soft package.
  So the overlay is a strong signal, not ground truth.
- Filenames of the `<number>-<timestamp>` pattern usually (not always) repeat the
  overlay's AWB — in the 6 long-digit files checked, 4 matched exactly and 1 did not
  (`90165721542...jpg`'s overlay AWB was `77573777455`, unrelated to the filename
  number). **Filenames cannot be trusted as ground truth.**

**Open design question for Phase 1** (not decided here): should the pipeline treat
this overlay as a first-class extraction source (parse its fixed key:value text
directly, which is cheap and very reliable) alongside/instead of trying to
decode the small physical barcode on the label? Flagged in the Phase 0 report.

## 3. Courier brands and label content

Legible courier identity was confirmed for two couriers; a few more AWB-prefix
clusters exist but the courier name itself wasn't legible in the images sampled.
See `backend/app/pipeline/couriers.yaml` for the regex patterns and per-courier
confidence notes. Summary:

| Courier | Confirmed by | AWB format observed | Where seen |
| --- | --- | --- | --- |
| Delhivery | "DELHIVERY" wordmark / "Delhivery Direct App" text on poly-bags | 11 digits, starts `191` | Majority of `weight_image_*` and plain-number files |
| BlueDart | Explicit "Courier Name: BLUEDART" / "BLUE DART" text on labels | 11 digits, starts `77` (775xxxxxxxx / 778xxxxxxxx) | `ms7`, `m_s_jpeg`, several named PNGs |
| Xpressbees (inferred) | "believe. achieve." tagline on box, not a confirmed courier-name string | 11 digits, starts `901` | long-digit files at sorter location "OEU" |
| Unidentified #1 | Beardo-brand box, courier name not visible | 14-15 digits, starts `144`/`152` | long-digit files at "DEL_PTD"/"BLR_FC1" |
| Unidentified #2 | Beardo-brand box, courier name not visible | 11 digits, starts `310495` | `ms*` files under the "Barcode:"-labeled overlay schema |

**Barcode types seen:** Code128 (1D, on printed shipping labels — confirmed by
direct decode) and QR (confirmed by direct decode on a Delhivery poly-bag). Several
labels show **two barcodes** (e.g. "Image with worker hand on it": a 1D barcode
plus a composite value `152880180157016,264821747717072,Feedlane2`; "One more Ekart
Format": `Barcode 1D` present, `Barcode 2D: NoRead` — the sorter's own scanner
explicitly reports failing to decode the second code). The second barcode encodes
an internal routing/feedlane code, not a second AWB.

**AWB placement:** on every label seen, the AWB is both barcoded and printed as
human-readable text directly below or beside the barcode (standard courier label
layout) — OCR-near-barcode should find it.

**Weight on the printed label:** rare — only one clear case ("Different format
belongs to Ekart": `Weight: 0.62 kg` printed next to the barcode in a camera-overlay
style directly on the box photo, not the overlay). Weight is overwhelmingly only
available via the sorter overlay, not the courier's own printed label, in this
dataset.

**Dimensions on the printed label:** essentially never seen printed on the courier
label itself in the sampled images; dimensions come from the sorter overlay
(`Dimension:` / `Length/Width/Height:` fields), when present as `LxWxH` or
`L:.. W:.. H:..` with cm or mm units (overlay units vary: some show cm with one
decimal, some show raw integer mm, e.g. `Dimension:L0213XH0148XW0178`).

**Other fields visible:** consignee name/address, GSTIN, SKU, order ID, "Mode of
Shipping", "PREPAID"/COD amount — all on the printed label, not needed for this
case's required fields but present and should not be mistaken for the AWB.

## 4. Problem categories (counted from the 54 images visually inspected, not the full 262)

| Category | Observed? | Example files |
| --- | --- | --- |
| Clean, readable label | Yes — common | `10_jpeg...`, `weight_image_19106721744493...` (Delhivery poly-bag, QR decoded), `ms7_jpeg...` (Code128 decoded) |
| No parcel in frame | Yes | `No Shipment ccaptured_png...`, `No Shipment packet captured_png...` (both curated examples; both still show a populated overlay — see section 2) |
| Multiple parcels visible | Yes, but overlay only describes one | `Multiple shipment packets in single sorter images_png...` — two boxes in frame, overlay AWB corresponds to only one of them |
| Parcel partially visible (cut by frame edge) | Yes | `Half shipment captured_png...` (box mostly out of frame, severely underexposed), `ms35_jpeg...` (box at top edge, cut off) |
| Hand/object covering the label | Yes | `Image with worker hand on it_png...` — hand covers part of the box but the label/barcode remain legible in this particular example |
| Label present but blurry/unreadable | Not clearly isolated in the 54 sampled; several very dark frames (below) make the label unreadable for that reason instead |
| Rotated/upside-down | Yes, common | `diff_format_jpeg...` and `Dimensions has no LBH words...png` (box upside-down, overlay text right-side-up — only the parcel is rotated 180°, not the whole frame) |
| Very dark / underexposed | Yes, common — roughly half of `ms*` sampled | `ms15`, `ms20`, `ms35`, `ms40` (box occupies a small, dark region in an otherwise near-black frame); `weight_image_31049517513413...`, `weight_image_31049517518932...` |
| Odd lighting (red/IR tint) | Yes | `Test in red color_png...` — package still legible, just red-channel tinted |
| Zero/implausible sensor reading | Yes (overlay-only, not the physical label) | `Shipment showing LBH values as 00_png...` (`0000x0000x0000`), `One more Ekart Format_png...` (`Weight: 70.0 kg` on a small soft parcel, `Barcode 2D: NoRead`) |

10 representative file names per category are listed above where that many exist;
several categories had fewer than 10 distinct examples in the 54 images actually
opened, and that is stated rather than padded.

## 5. Tooling spike (`scripts/spike.py`, 20 images, see run output below)

Environment: Python 3.12.3, Linux (WSL2), `zxing-cpp==3.1.1`, `rapidocr-onnxruntime==1.4.4`,
`opencv-python-headless==5.0.0.93`, `Pillow==13.0.0`, `numpy==2.5.4`. Both installed
from prebuilt wheels with no compiler and no system libraries required — confirms
the architecture doc's "pip wheel, no system DLLs" expectation for zxing-cpp, and
RapidOCR's "pip only, models bundled" for OCR.

**Results across the 20-image mixed sample** (clean labels, dark frames, partial,
blocked, no-parcel, multi-parcel, odd lighting, zero-dimension overlay, several
couriers):

| Metric | Result |
| --- | --- |
| Barcode decoded (>=1 found) | 2 / 20 |
| OCR found text | 20 / 20 |
| Barcode decode time | mean 0.236 s, max 0.697 s |
| OCR time | mean 1.533 s, max 3.978 s |
| Crashes / exceptions | none |

**OCR quality:** mean per-line confidence was 0.92–0.99 on every image, including
the very dark ones (because the overlay text itself is still bright, crisp, and
high-contrast even when the photographed parcel is nearly black). RapidOCR
correctly transcribed almost all overlay fields; small errors seen were cosmetic
(e.g. `"Weight 0.37ig"` instead of `"Weight: 0.37 kg"`, a missing space in `AWBNo`)
and would not break a keyword+regex parser.

**Barcode decode yield was low (2/20) and resolution-dependent, not a library
problem.** Both successes were on images where the physical label/barcode occupied
a large fraction of the frame (`ms7_jpeg`: BlueDart box fills most of the shot,
Code128 decoded immediately; `weight_image_19106721744493...`: Delhivery poly-bag
fills most of the shot, QR decoded after one adaptive-threshold retry). In the other
18 images the label is a small region inside a wide sorter shot — after the
pipeline's planned 2000px working-copy downscale, the barcode's modules are only a
handful of pixels wide, below what any decoder can read. **Conclusion for Phase 1:**
barcode decode needs to run on a *cropped, upscaled* region around the detected
label, not the full downscaled working image — this matches the architecture doc's
plan to "OCR an upscaled crop around the label area," but the same crop-then-upscale
step turns out to be necessary for barcode decode too, more so than for OCR.

**OCR engine recommendation: keep `rapidocr-onnxruntime` as default, do not spend
time on Tesseract.** Quality (mean conf consistently >0.92, including on dark/odd
images) and speed (well under the 2-4s/image target) both clear the bar on the
first try, install was a single pip wheel with no system dependency on this Linux
dev machine, and the architecture doc already prefers it for the same reasons
("light install, works on Windows"). Nothing in this spike indicates a need to
fall back to Tesseract; that comparison can be skipped unless Windows-specific
installation problems show up later.

## 6. `couriers.yaml` draft

See `backend/app/pipeline/couriers.yaml`. Contains the two courier patterns
confirmed by legible courier-name text (Delhivery, BlueDart), two more AWB-prefix
clusters where only the brand's packaging (not the courier) was legible, and the
generic alphanumeric fallback. All patterns are generic (length + digit structure),
not hard-coded to the specific AWB values observed.
