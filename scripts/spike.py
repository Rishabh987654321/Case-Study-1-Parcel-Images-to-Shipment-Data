"""Phase 0 tooling spike: barcode + OCR on a curated sample of sample_data/raw.

Not part of the pipeline. Run with the Phase 0 venv active:
    python scripts/spike.py
Prints per-image results and aggregate timing/quality stats used to pick the
OCR engine and confirm zxing-cpp works on this machine (see docs/dataset-notes.md).
"""
import time
from pathlib import Path

import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

RAW_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "raw"

# A deliberately mixed set: clean labels, dark/underexposed, partial, blocked,
# no-parcel, multiple-parcel, odd lighting, zero-dimension overlay, several couriers.
SAMPLE_FILES = [
    "10_jpeg.rf.XFK2Hy0xpa8FkMppr5ZH.jpeg",
    "1_jpeg.rf.TmrbSjoSNip5rNFlk3SV.jpeg",
    "No Shipment packet captured_png.rf.1VvRtdnwIQAHs1Q83pHV.png",
    "Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png",
    "Half shipment captured_png.rf.WNrelVB6aeQO3rpN0eiY.png",
    "Image with worker hand on it_png.rf.BIEVZtagxVrux0bDKfYR.png",
    "Test in red color_png.rf.mhBudpH2mZ2NBKAb8Siv.png",
    "One more Ekart Format_png.rf.RjFc1ZG8LMmkelg5D2W8.png",
    "Shipment showing LBH values as 00_png.rf.RjUz8FS62U9fGgE7Kt4s.png",
    "14408950450567-20250604011353_jpg.rf.iuZ60Q278JrHYD9iPuIo.jpg",
    "152907240809514-20250609194849_jpg.rf.fhnR0y3bAXFH3zWznGW5.jpg",
    "90147261525_jpg.rf.Cu1JLbFbYImktV6LoP61.jpg",
    "90165721542_jpg.rf.tmiPdacUZMhfjcFUKgCp.jpg",
    "ms15_jpeg.rf.HFPjgPKbvtU07NDuzfmt.jpeg",
    "ms35_jpeg.rf.uhAPuIGkAWtjcbmZRELD.jpeg",
    "ms40_jpeg.rf.zsOgJwQv19F13cX4oE1V.jpeg",
    "ms7_jpeg.rf.EHDLSQ4QvrAAUe0Y73CJ.jpeg",
    "weight_image_19106721560684_1748746193528_jpg.rf.H81HmQfPPmHhu9xXk1mS.jpg",
    "weight_image_19106721744493_1753155100459_jpg.rf.zEgx7vdgfqUNrMmUv2qH.jpg",
    "weight_image_31049517513413_1751190361265_jpg.rf.AeMEie43C82H9GsedUnG.jpg",
]

MAX_SIDE = 2000  # same working-copy cap the real pipeline will use


def load_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)  # no-op here (no EXIF in this dataset), kept for real inputs
        im = im.convert("RGB")
        if max(im.size) > MAX_SIDE:
            scale = MAX_SIDE / max(im.size)
            im = im.resize((int(im.width * scale), int(im.height * scale)))
        arr = np.array(im)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def decode_barcodes(bgr: np.ndarray):
    """Retry cascade: original -> gray+CLAHE -> adaptive threshold -> rotations."""
    attempts = []

    t0 = time.perf_counter()
    found = zxingcpp.read_barcodes(bgr)
    attempts.append(("original", time.perf_counter() - t0, len(found)))
    if found:
        return found, attempts

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    t0 = time.perf_counter()
    found = zxingcpp.read_barcodes(enhanced)
    attempts.append(("gray+clahe", time.perf_counter() - t0, len(found)))
    if found:
        return found, attempts

    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 10
    )
    t0 = time.perf_counter()
    found = zxingcpp.read_barcodes(thresh)
    attempts.append(("adaptive_threshold", time.perf_counter() - t0, len(found)))
    if found:
        return found, attempts

    for angle in (90, 180):
        rotated = cv2.rotate(
            bgr,
            cv2.ROTATE_90_CLOCKWISE if angle == 90 else cv2.ROTATE_180,
        )
        t0 = time.perf_counter()
        found = zxingcpp.read_barcodes(rotated)
        attempts.append((f"rotate_{angle}", time.perf_counter() - t0, len(found)))
        if found:
            return found, attempts

    return [], attempts


def main() -> None:
    ocr = RapidOCR()

    barcode_hits = 0
    ocr_hits = 0
    barcode_times = []
    ocr_times = []
    issues = []

    for name in SAMPLE_FILES:
        path = RAW_DIR / name
        if not path.exists():
            issues.append(f"MISSING FILE: {name}")
            continue

        print("=" * 100)
        print(f"FILE: {name}")
        try:
            bgr = load_bgr(path)
        except Exception as e:  # noqa: BLE001 - recon script
            issues.append(f"LOAD FAILED: {name}: {e}")
            print(f"  load failed: {e}")
            continue
        print(f"  working size: {bgr.shape[1]}x{bgr.shape[0]}")

        try:
            barcodes, attempts = decode_barcodes(bgr)
        except Exception as e:  # noqa: BLE001
            issues.append(f"BARCODE CRASH: {name}: {e}")
            barcodes, attempts = [], []
            print(f"  barcode decode crashed: {e}")
        total_barcode_time = sum(t for _, t, _ in attempts)
        barcode_times.append(total_barcode_time)
        if barcodes:
            barcode_hits += 1
        print(f"  barcode attempts: {[(a, round(t, 3), n) for a, t, n in attempts]}")
        for b in barcodes:
            print(f"    -> {b.format} | {b.text!r} | valid={b.valid}")

        try:
            t0 = time.perf_counter()
            result, _ = ocr(bgr)
            ocr_time = time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001
            issues.append(f"OCR CRASH: {name}: {e}")
            result, ocr_time = None, 0.0
            print(f"  OCR crashed: {e}")
        ocr_times.append(ocr_time)

        if result:
            ocr_hits += 1
            lines = [r[1] for r in result]
            confs = [r[2] for r in result]
            joined = " | ".join(lines)[:200]
            mean_conf = sum(confs) / len(confs)
            print(f"  OCR: {len(result)} lines, mean_conf={mean_conf:.2f}, time={ocr_time:.2f}s")
            print(f"  OCR text (first 200 chars): {joined}")
        else:
            print(f"  OCR: no text found, time={ocr_time:.2f}s")

    n = len(SAMPLE_FILES)
    print("=" * 100)
    print("AGGREGATE STATS")
    print(f"  images attempted: {n}")
    print(f"  barcode decoded (>=1 found): {barcode_hits}/{n}")
    print(f"  OCR found text: {ocr_hits}/{n}")
    if barcode_times:
        print(f"  barcode time: mean={sum(barcode_times)/len(barcode_times):.3f}s max={max(barcode_times):.3f}s")
    if ocr_times:
        print(f"  OCR time: mean={sum(ocr_times)/len(ocr_times):.3f}s max={max(ocr_times):.3f}s")
    if issues:
        print("  issues:")
        for i in issues:
            print(f"    - {i}")
    else:
        print("  issues: none")


if __name__ == "__main__":
    main()
