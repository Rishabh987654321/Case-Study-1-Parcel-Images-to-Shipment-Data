"""Stress test (docs/phases.md Phase 6, task 2): process 300+ images in one
batch against a live HTTP server + real worker-pool subprocesses, to check the
system holds up at roughly 2x the size of the full sample dataset.

Uploads all 262 sample_data/raw images plus a second, byte-distinct copy of
each (524 total, one batch). The second copy is re-saved at a slightly
different JPEG quality / as PNG so its sha256 differs from the original -
uploading byte-identical content would just trigger this app's own
same-batch DUPLICATE_IMAGE dedup and reuse the first copy's result instead of
genuinely processing a second image, which would undercount the real work
done and defeat the point of a throughput/memory stress test.

Run from the repo root (needs the backend venv active):
    python scripts/stress_test.py
"""
import io
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
SAMPLE_DIR = ROOT / "sample_data" / "raw"
SCRATCH_DIR = ROOT / "scripts" / "_stress_test_data"
DUPLICATE_DIR = SCRATCH_DIR / "duplicates"
PORT = 8932
BASE_URL = f"http://127.0.0.1:{PORT}/api"
CHUNK_SIZE = 10
POLL_INTERVAL_S = 2.0
RECORDS_PAGE_SIZE = 200


def _wait_for_server(client: httpx.Client, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(0.3)
    raise RuntimeError("server did not come up in time")


def _process_tree_rss_kb(root_pid: int) -> int:
    try:
        out = subprocess.run(["ps", "-eo", "pid,ppid,rss", "--no-headers"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        pid, ppid, kb = (int(p) for p in parts)
        rss[pid] = kb
        children.setdefault(ppid, []).append(pid)

    total = 0
    stack = [root_pid]
    seen: set[int] = set()
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in rss:
            continue
        seen.add(pid)
        total += rss[pid]
        stack.extend(children.get(pid, []))
    return total


def _make_byte_distinct_copy(src: Path, dst: Path) -> None:
    """Re-encodes the image so its bytes (and sha256) differ from the
    original, while the pixel content stays visually the same - avoids this
    app's own duplicate-image dedup collapsing the stress test back down to
    only 262 genuinely-processed images."""
    img = Image.open(src).convert("RGB")
    if src.suffix.lower() in (".jpg", ".jpeg"):
        img.save(dst, format="JPEG", quality=92)  # default save quality differs from the original's
    else:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # Flip one harmless trailing byte's worth of difference by re-encoding
        # through a different PNG compression level, guaranteeing distinct bytes.
        buf2 = io.BytesIO()
        img.save(buf2, format="PNG", compress_level=1)
        dst.write_bytes(buf2.getvalue() if buf2.getvalue() != buf.getvalue() else buf.getvalue() + b"\x00")


def _fetch_all_records(client: httpx.Client, batch_id: str) -> list[dict]:
    records: list[dict] = []
    page = 1
    while True:
        body = client.get(f"/batches/{batch_id}/records", params={"page": page, "page_size": RECORDS_PAGE_SIZE}).json()
        records.extend(body["items"])
        if len(records) >= body["total"]:
            return records
        page += 1


def main() -> None:
    if not SAMPLE_DIR.exists():
        raise SystemExit(f"sample data not found at {SAMPLE_DIR}")
    originals = sorted(p for p in SAMPLE_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    print(f"Found {len(originals)} original images; building {len(originals)} byte-distinct duplicates...")

    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR)
    DUPLICATE_DIR.mkdir(parents=True)
    for p in originals:
        _make_byte_distinct_copy(p, DUPLICATE_DIR / f"dup_{p.name}")
    duplicates = sorted(DUPLICATE_DIR.iterdir())
    all_images = originals + duplicates
    print(f"Total images for this batch: {len(all_images)}")

    env = {**os.environ, "DATA_DIR": str(SCRATCH_DIR / "server_data"), "LOG_LEVEL": "WARNING"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )

    peak_rss_kb = 0
    accepted_total = 0
    rejected_total = 0
    records: list[dict] = []
    final_summary: dict = {}
    upload_elapsed = 0.0
    process_elapsed = 0.0

    try:
        with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
            _wait_for_server(client)
            peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))

            batch_id = client.post("/batches", json={"name": "stress-test-524"}).json()["batch_id"]
            print(f"Created batch {batch_id}")

            t_upload_start = time.perf_counter()
            for i in range(0, len(all_images), CHUNK_SIZE):
                chunk = all_images[i : i + CHUNK_SIZE]
                files = [("files", (p.name, p.read_bytes(), "image/jpeg" if p.suffix.lower() != ".png" else "image/png")) for p in chunk]
                r = client.post(f"/batches/{batch_id}/images", files=files)
                r.raise_for_status()
                body = r.json()
                accepted_total += len(body["accepted"])
                rejected_total += len(body["rejected"])
                peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))
                if (i // CHUNK_SIZE) % 10 == 0:
                    print(f"  uploaded {min(i + CHUNK_SIZE, len(all_images))}/{len(all_images)}")
            upload_elapsed = time.perf_counter() - t_upload_start
            print(f"Upload done in {upload_elapsed:.1f}s: {accepted_total} accepted, {rejected_total} rejected")

            client.post(f"/batches/{batch_id}/finalize")

            t_process_start = time.perf_counter()
            last_processed = -1
            stall_count = 0
            while True:
                summary = client.get(f"/batches/{batch_id}").json()
                peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))
                if summary["processed"] != last_processed:
                    print(
                        f"  processed {summary['processed']}/{summary['total_images']} "
                        f"({summary['progress_pct']}%) status={summary['status']} eta={summary['eta_seconds']}s "
                        f"rss={peak_rss_kb / 1024:.0f}MB"
                    )
                    last_processed = summary["processed"]
                    stall_count = 0
                else:
                    stall_count += 1
                if summary["status"] in ("completed", "completed_with_errors"):
                    final_summary = summary
                    break
                if stall_count > 150:  # 5 minutes with zero progress - something's actually hung, not just slow
                    raise RuntimeError(f"batch appears hung: {summary}")
                time.sleep(POLL_INTERVAL_S)
            process_elapsed = time.perf_counter() - t_process_start
            print(f"Processing done in {process_elapsed:.1f}s")

            records = _fetch_all_records(client, batch_id)
            csv_bytes = client.get(f"/batches/{batch_id}/export.csv").content
            (SCRATCH_DIR / "export.csv").write_bytes(csv_bytes)
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()

    processing_ms = sorted(r["processing_ms"] for r in records if r["processing_ms"])
    mean_s = statistics.mean(processing_ms) / 1000 if processing_ms else 0
    p95_s = processing_ms[int(len(processing_ms) * 0.95) - 1] / 1000 if processing_ms else 0
    images_per_min = (accepted_total / process_elapsed) * 60 if process_elapsed else 0

    csv_row_count = max(0, len(SCRATCH_DIR.joinpath("export.csv").read_text(encoding="utf-8-sig").splitlines()) - 1)

    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY (524-image batch)")
    print(f"  images found:          {len(all_images)} ({len(originals)} original + {len(duplicates)} byte-distinct duplicates)")
    print(f"  accepted / rejected:   {accepted_total} / {rejected_total}")
    print(f"  upload wall time:      {upload_elapsed:.1f}s")
    print(f"  processing wall time:  {process_elapsed:.1f}s ({process_elapsed / 60:.1f} min)")
    print(f"  throughput:            {images_per_min:.1f} images/min")
    print(f"  mean time/image:       {mean_s:.2f}s")
    print(f"  p95 time/image:        {p95_s:.2f}s")
    print(f"  peak RSS (server tree):{peak_rss_kb / 1024:.0f} MB")
    print(f"  final batch status:    {final_summary.get('status')}")
    print(f"  status counts:         {final_summary.get('counts')}")
    print(f"  CSV row count:         {csv_row_count} (accepted: {accepted_total}, match: {csv_row_count == accepted_total})")
    print(f"\nNo hang, no crash: {'YES' if final_summary.get('status') in ('completed', 'completed_with_errors') else 'NO - see above'}")
    print(f"Scratch data (export.csv) left at {SCRATCH_DIR} for inspection.")


if __name__ == "__main__":
    main()
