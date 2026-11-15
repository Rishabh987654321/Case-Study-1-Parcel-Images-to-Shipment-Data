"""Robustness evaluation (Phase 5 task 3, docs/phases.md): create augmented
copies of the ground-truth images, run the pipeline on each augmentation set,
and compare against the un-augmented baseline. A good result looks like
"recall drops but wrong-extraction stays near zero" - augmentation should make
the system abstain more, not guess wrong more.

Usage (from backend/, with the venv active, after the normal eval run):
    python ../eval/augment.py --out-report ../eval/reports/robustness_YYYYMMDD.md

Only augments the 38 ground-truth images (not the full 262-image dataset) to
keep this bounded - it's a robustness check, not a full re-evaluation.
"""
import argparse
import csv
import random
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
RAW_DIR = REPO_ROOT / "sample_data" / "raw"
GROUND_TRUTH = REPO_ROOT / "eval" / "ground_truth.csv"
AUGMENTED_DIR = REPO_ROOT / "eval" / "augmented"

_CROP_SEED = 20261114  # fixed seed so the "random" crop is reproducible across runs


def _load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def aug_rotate90(img: Image.Image, _rng: random.Random) -> Image.Image:
    return img.rotate(-90, expand=True)


def aug_rotate180(img: Image.Image, _rng: random.Random) -> Image.Image:
    return img.rotate(180)


def aug_downscale50(img: Image.Image, _rng: random.Random) -> Image.Image:
    w, h = img.size
    return img.resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS)


def aug_blur5x5(img: Image.Image, _rng: random.Random) -> Image.Image:
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    blurred = cv2.GaussianBlur(arr, (5, 5), 0)
    return Image.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))


def aug_brightness_minus30(img: Image.Image, _rng: random.Random) -> Image.Image:
    return ImageEnhance.Brightness(img).enhance(0.7)


def aug_brightness_plus30(img: Image.Image, _rng: random.Random) -> Image.Image:
    return ImageEnhance.Brightness(img).enhance(1.3)


def aug_jpeg_q40(img: Image.Image, _rng: random.Random) -> Image.Image:
    import io

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=40)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def aug_crop_5_10pct(img: Image.Image, rng: random.Random) -> Image.Image:
    w, h = img.size
    left_pct, right_pct = rng.uniform(0.05, 0.10), rng.uniform(0.05, 0.10)
    top_pct, bottom_pct = rng.uniform(0.05, 0.10), rng.uniform(0.05, 0.10)
    box = (int(w * left_pct), int(h * top_pct), int(w * (1 - right_pct)), int(h * (1 - bottom_pct)))
    return img.crop(box)


AUGMENTATIONS = {
    "rotate90": aug_rotate90,
    "rotate180": aug_rotate180,
    "downscale50": aug_downscale50,
    "blur5x5": aug_blur5x5,
    "brightness_minus30": aug_brightness_minus30,
    "brightness_plus30": aug_brightness_plus30,
    "jpeg_q40": aug_jpeg_q40,
    "crop_5_10pct": aug_crop_5_10pct,
}


def load_ground_truth_names() -> list[str]:
    with open(GROUND_TRUTH, encoding="utf-8-sig") as f:
        return [row["image_name"] for row in csv.DictReader(f)]


def build_augmented_sets(names: list[str]) -> None:
    if AUGMENTED_DIR.exists():
        shutil.rmtree(AUGMENTED_DIR)
    for aug_name, fn in AUGMENTATIONS.items():
        out_dir = AUGMENTED_DIR / aug_name
        out_dir.mkdir(parents=True)
        rng = random.Random(_CROP_SEED)
        for name in names:
            src = RAW_DIR / name
            if not src.exists():
                continue
            img = _load_rgb(src)
            augmented = fn(img, rng)
            out_path = out_dir / name
            # Keep the exact original filename+extension (needed to match rows in
            # ground_truth.csv by name). jpeg_q40's degradation is already baked
            # into the pixel data from its in-memory JPEG round-trip above, so the
            # final on-disk save just matches the source format - no need to
            # re-encode as JPEG again under a possibly-.png filename.
            fmt = "JPEG" if src.suffix.lower() in (".jpg", ".jpeg") else "PNG"
            augmented.save(out_path, format=fmt)


def run_pipeline(folder: Path, out_csv: Path, out_json: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "app.pipeline.cli", str(folder), "--out", str(out_csv), "--json", str(out_json)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
    )


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def compute_metrics(results: list[dict], truth: list[dict]) -> dict:
    """Mirrors eval/run_eval.py's headline metrics (wrong-extraction rate, AWB
    recall, silent-miss rate) - kept as a small, self-contained subset here
    rather than importing run_eval.py, since this script only needs those three."""
    results_by_name = {r["image_name"]: r for r in results}
    truth_by_name = {t["image_name"]: t for t in truth}
    rows = [(name, t, results_by_name[name]) for name, t in truth_by_name.items() if name in results_by_name]

    truth_ok = [row for row in rows if row[1]["truth_status"] == "OK"]
    pred_ok = [row for row in rows if row[2]["status"] == "OK"]
    wrong_extractions = [row for row in pred_ok if row[2]["awb"] != row[1]["truth_awb"]]
    correct_ok_awb = [row for row in pred_ok if row[1]["truth_status"] == "OK" and row[2]["awb"] == row[1]["truth_awb"]]
    truth_flagged = [row for row in rows if row[1]["truth_status"] == "FLAGGED"]
    silent_misses = [row for row in truth_flagged if row[2]["status"] == "OK"]
    status_counts: dict[str, int] = {}
    for _, _, r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    return {
        "n": len(rows),
        "missing": len(truth_by_name) - len(rows),
        "wrong_extraction_rate": len(wrong_extractions) / len(pred_ok) if pred_ok else 0.0,
        "wrong_extractions_n": len(wrong_extractions),
        "pred_ok_n": len(pred_ok),
        "awb_recall": len(correct_ok_awb) / len(truth_ok) if truth_ok else 0.0,
        "truth_ok_n": len(truth_ok),
        "silent_miss_rate": len(silent_misses) / len(truth_flagged) if truth_flagged else 0.0,
        "truth_flagged_n": len(truth_flagged),
        "status_counts": status_counts,
        "wrong_extraction_names": [name for name, _, _ in wrong_extractions],
    }


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--baseline-results", type=Path, default=None, help="existing results.csv for the un-augmented baseline; re-runs the CLI on sample_data/raw ground-truth subset if omitted")
    args = parser.parse_args()

    names = load_ground_truth_names()
    truth = load_csv(GROUND_TRUTH)
    print(f"Augmenting {len(names)} ground-truth images across {len(AUGMENTATIONS)} augmentation types...")
    build_augmented_sets(names)

    work_dir = REPO_ROOT / "eval" / "_augment_work"
    work_dir.mkdir(exist_ok=True)

    if args.baseline_results and args.baseline_results.exists():
        baseline_results = load_csv(args.baseline_results)
    else:
        baseline_dir = work_dir / "baseline"
        baseline_dir.mkdir(exist_ok=True)
        for name in names:
            src = RAW_DIR / name
            if src.exists():
                shutil.copy(src, baseline_dir / name)
        base_csv, base_json = work_dir / "baseline.csv", work_dir / "baseline.json"
        print("Running baseline (un-augmented) pipeline for comparison...")
        run_pipeline(baseline_dir, base_csv, base_json)
        baseline_results = load_csv(base_csv)

    baseline_metrics = compute_metrics(baseline_results, truth)

    per_aug: dict[str, dict] = {}
    for aug_name in AUGMENTATIONS:
        print(f"Running pipeline on '{aug_name}' ({len(names)} images)...")
        out_csv, out_json = work_dir / f"{aug_name}.csv", work_dir / f"{aug_name}.json"
        run_pipeline(AUGMENTED_DIR / aug_name, out_csv, out_json)
        aug_results = load_csv(out_csv)
        per_aug[aug_name] = compute_metrics(aug_results, truth)

    lines = []
    lines.append("# Robustness evaluation (Phase 5 task 3)\n")
    lines.append(
        "Augmented copies of all 38 ground-truth images, one augmentation at a time (not stacked), "
        f"run through the same pipeline (`backend/app/pipeline/cli.py`). Crop augmentation uses a fixed "
        f"random seed ({_CROP_SEED}) for reproducibility.\n"
    )
    lines.append("## Baseline (un-augmented, for comparison)\n")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Wrong-extraction rate | {fmt_pct(baseline_metrics['wrong_extraction_rate'])} ({baseline_metrics['wrong_extractions_n']}/{baseline_metrics['pred_ok_n']} predicted-OK) |")
    lines.append(f"| AWB recall | {fmt_pct(baseline_metrics['awb_recall'])} (of {baseline_metrics['truth_ok_n']} truth-OK) |")
    lines.append(f"| Silent-miss rate | {fmt_pct(baseline_metrics['silent_miss_rate'])} |")
    lines.append(f"| Status counts | {baseline_metrics['status_counts']} |\n")

    lines.append("## Per-augmentation results\n")
    lines.append("| Augmentation | Wrong-extraction rate | AWB recall | Silent-miss rate | Status counts |")
    lines.append("| --- | --- | --- | --- | --- |")
    for aug_name, m in per_aug.items():
        lines.append(
            f"| {aug_name} | {fmt_pct(m['wrong_extraction_rate'])} ({m['wrong_extractions_n']}/{m['pred_ok_n']}) | "
            f"{fmt_pct(m['awb_recall'])} | {fmt_pct(m['silent_miss_rate'])} | {m['status_counts']} |"
        )

    baseline_wrong_names = set(baseline_metrics["wrong_extraction_names"])
    lines.append("\n## Interpretation\n")
    for aug_name, m in per_aug.items():
        recall_delta = m["awb_recall"] - baseline_metrics["awb_recall"]
        wrong_delta = m["wrong_extraction_rate"] - baseline_metrics["wrong_extraction_rate"]
        verdict = "GOOD (recall dropped, wrong-extraction did not rise)" if recall_delta <= 0 and wrong_delta <= 0.01 else "WATCH (wrong-extraction rate increased)" if wrong_delta > 0.01 else "mixed"
        lines.append(f"- **{aug_name}**: recall {recall_delta:+.1%}, wrong-extraction {wrong_delta:+.1%} -> {verdict}")
        new_wrong = [n for n in m["wrong_extraction_names"] if n not in baseline_wrong_names]
        persisting_wrong = [n for n in m["wrong_extraction_names"] if n in baseline_wrong_names]
        if new_wrong:
            lines.append(f"  - NEW wrong-extraction cases (not wrong at baseline): {', '.join(new_wrong)}")
        if persisting_wrong:
            lines.append(f"  - pre-existing wrong-extraction case, unaffected by this augmentation: {', '.join(persisting_wrong)}")

    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {args.out_report}")


if __name__ == "__main__":
    main()
