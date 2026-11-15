"""CLI entry point: python -m app.pipeline.cli <folder> --out results.csv --json results.json

Runs the pipeline on every image in a folder without any web code, so accuracy
can be measured before the API/UI exist (docs/phases.md Phase 1).
"""
import argparse
import csv
import dataclasses
import json
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

from app.config import IMAGE_TIMEOUT_S
from app.pipeline.runner import build_error_record, process_image
from app.pipeline.types import ResultRecord

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

CSV_COLUMNS = [
    "image_name", "status", "primary_flag", "flag_reason", "awb", "weight_kg",
    "length_cm", "width_cm", "height_cm", "courier", "confidence", "awb_suggestion",
    "warnings", "awb_source", "weight_raw", "dimensions_raw", "batch_id", "processed_at",
]
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _record_to_csv_row(r: ResultRecord, batch_id: str) -> list[str]:
    return [
        _csv_safe(r.filename),
        _csv_safe(r.status),
        _csv_safe(r.primary_flag or ""),
        _csv_safe(r.flag_reason or ""),
        _csv_safe(r.awb or ""),
        _csv_safe(r.weight_kg if r.weight_kg is not None else ""),
        _csv_safe(r.length_cm if r.length_cm is not None else ""),
        _csv_safe(r.width_cm if r.width_cm is not None else ""),
        _csv_safe(r.height_cm if r.height_cm is not None else ""),
        _csv_safe(r.courier or ""),
        _csv_safe(f"{r.confidence:.2f}"),
        _csv_safe(r.awb_suggestion or ""),
        _csv_safe(";".join(r.warnings)),
        _csv_safe(r.awb_source or ""),
        _csv_safe(r.weight_raw or ""),
        _csv_safe(r.dimensions_raw or ""),
        _csv_safe(batch_id),
        _csv_safe(r.processed_at),
    ]


def _result_to_jsonable(r: ResultRecord) -> dict:
    d = dataclasses.asdict(r)
    return d


def discover_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)


def _worker(path_str: str, name: str) -> ResultRecord:
    return process_image(path_str, name)


def run_folder(folder: Path, worker_count: int | None = None) -> list[ResultRecord]:
    images = discover_images(folder)
    total = len(images)
    worker_count = worker_count or max(1, (os.cpu_count() or 2) - 1)
    results: list[ResultRecord] = []

    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(_worker, str(p), p.name): p for p in images}
        for done, (future, path) in enumerate(futures.items(), start=1):
            name = path.name
            print(f"Processing image {done}/{total}: {name}...")
            try:
                record = future.result(timeout=IMAGE_TIMEOUT_S)
            except FutureTimeoutError:
                record = build_error_record(name, name, "PROCESSING_ERROR", f"Timed out after {IMAGE_TIMEOUT_S}s", time.perf_counter())
            except Exception as e:  # noqa: BLE001 - a worker crash must not stop the batch
                record = build_error_record(name, name, "PROCESSING_ERROR", str(e), time.perf_counter())
            results.append(record)
            flag = f" [{record.primary_flag}]" if record.primary_flag else ""
            print(f"  -> {record.status}{flag} awb={record.awb or '-'}")

    order = {p.name: i for i, p in enumerate(images)}
    results.sort(key=lambda r: order.get(r.filename, 0))
    return results


def write_csv(results: list[ResultRecord], out_path: Path, batch_id: str = "") -> None:
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in results:
            writer.writerow(_record_to_csv_row(r, batch_id))


def write_json(results: list[ResultRecord], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([_result_to_jsonable(r) for r in results], f, indent=2, default=str)


def print_summary(results: list[ResultRecord], elapsed_s: float) -> None:
    status_counts = Counter(r.status for r in results)
    flag_counts = Counter(r.primary_flag for r in results if r.primary_flag)
    times_ms = sorted(r.processing_ms for r in results)
    mean_ms = sum(times_ms) / len(times_ms) if times_ms else 0
    p95_ms = times_ms[int(len(times_ms) * 0.95) - 1] if times_ms else 0

    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  total images: {len(results)}")
    for status in ("OK", "FLAGGED", "ERROR"):
        print(f"  {status}: {status_counts.get(status, 0)}")
    if flag_counts:
        print("  by flag:")
        for flag, count in flag_counts.most_common():
            print(f"    {flag}: {count}")
    print(f"  mean time/image: {mean_ms:.0f} ms")
    print(f"  p95 time/image: {p95_ms:.0f} ms")
    print(f"  total elapsed: {elapsed_s:.1f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the parcel-label pipeline on a folder of images.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results.csv"))
    parser.add_argument("--json", type=Path, default=Path("results.json"))
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    t_start = time.perf_counter()
    results = run_folder(args.folder, args.workers)
    elapsed = time.perf_counter() - t_start

    write_csv(results, args.out)
    write_json(results, args.json)
    print_summary(results, elapsed)
    print(f"\nWrote {args.out} and {args.json}")


if __name__ == "__main__":
    main()
