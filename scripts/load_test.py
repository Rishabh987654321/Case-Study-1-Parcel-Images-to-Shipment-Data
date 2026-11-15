"""Load test: process the full sample_data/raw dataset through the real HTTP
API, backed by a live uvicorn server + real worker-pool subprocesses, and
report throughput/latency/memory - then diff the result against the Phase 1
CLI's output on the same images (docs/phases.md Phase 3, task 7).

Run from the repo root (needs the backend venv active):
    python scripts/load_test.py
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
SAMPLE_DIR = ROOT / "sample_data" / "raw"
SCRATCH_DIR = ROOT / "scripts" / "_load_test_data"  # throwaway, not backend/data
PORT = 8931
BASE_URL = f"http://127.0.0.1:{PORT}/api"
CHUNK_SIZE = 10
POLL_INTERVAL_S = 1.0
RECORDS_PAGE_SIZE = 200  # API caps page_size at 200 (see app/schemas.py)


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
    """Sum RSS (KB) for root_pid and all its descendants via /proc through
    `ps`, rather than adding psutil as a dependency for a one-off script."""
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
    images = sorted(p for p in SAMPLE_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    print(f"Found {len(images)} images in {SAMPLE_DIR}")

    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR)
    SCRATCH_DIR.mkdir(parents=True)

    env = {**os.environ, "DATA_DIR": str(SCRATCH_DIR), "LOG_LEVEL": "WARNING"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )

    peak_rss_kb = 0
    accepted_total = 0
    rejected_total = 0
    upload_elapsed = 0.0
    process_elapsed = 0.0
    records: list[dict] = []
    final_summary: dict = {}

    try:
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
            _wait_for_server(client)
            peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))

            batch_id = client.post("/batches", json={}).json()["batch_id"]
            print(f"Created batch {batch_id}")

            t_upload_start = time.perf_counter()
            for i in range(0, len(images), CHUNK_SIZE):
                chunk = images[i : i + CHUNK_SIZE]
                files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in chunk]
                r = client.post(f"/batches/{batch_id}/images", files=files)
                r.raise_for_status()
                body = r.json()
                accepted_total += len(body["accepted"])
                rejected_total += len(body["rejected"])
                peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))
                print(f"  uploaded {min(i + CHUNK_SIZE, len(images))}/{len(images)}")
            upload_elapsed = time.perf_counter() - t_upload_start
            print(f"Upload done in {upload_elapsed:.1f}s: {accepted_total} accepted, {rejected_total} rejected")

            client.post(f"/batches/{batch_id}/finalize")

            t_process_start = time.perf_counter()
            last_processed = -1
            while True:
                summary = client.get(f"/batches/{batch_id}").json()
                peak_rss_kb = max(peak_rss_kb, _process_tree_rss_kb(server.pid))
                if summary["processed"] != last_processed:
                    print(
                        f"  processed {summary['processed']}/{summary['total_images']} "
                        f"({summary['progress_pct']}%) status={summary['status']} eta={summary['eta_seconds']}s"
                    )
                    last_processed = summary["processed"]
                if summary["status"] in ("completed", "completed_with_errors"):
                    final_summary = summary
                    break
                time.sleep(POLL_INTERVAL_S)
            process_elapsed = time.perf_counter() - t_process_start
            print(f"Processing done in {process_elapsed:.1f}s")

            records = _fetch_all_records(client, batch_id)
            (SCRATCH_DIR / "export.csv").write_bytes(client.get(f"/batches/{batch_id}/export.csv").content)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()

    processing_ms = sorted(r["processing_ms"] for r in records if r["processing_ms"])
    mean_s = statistics.mean(processing_ms) / 1000 if processing_ms else 0
    p95_s = processing_ms[int(len(processing_ms) * 0.95) - 1] / 1000 if processing_ms else 0
    images_per_min = (accepted_total / process_elapsed) * 60 if process_elapsed else 0

    print("\n" + "=" * 60)
    print("LOAD TEST SUMMARY")
    print(f"  images found:          {len(images)}")
    print(f"  accepted / rejected:   {accepted_total} / {rejected_total}")
    print(f"  upload wall time:      {upload_elapsed:.1f}s")
    print(f"  processing wall time:  {process_elapsed:.1f}s")
    print(f"  throughput:            {images_per_min:.1f} images/min")
    print(f"  mean time/image:       {mean_s:.2f}s")
    print(f"  p95 time/image:        {p95_s:.2f}s")
    print(f"  peak RSS (server tree):{peak_rss_kb / 1024:.0f} MB")
    print(f"  final batch status:    {final_summary.get('status')}")
    print(f"  status counts:         {final_summary.get('counts')}")
    print(f"  flag counts:           {final_summary.get('flag_counts')}")

    cli_json = SCRATCH_DIR / "cli_results.json"
    cli_csv = SCRATCH_DIR / "cli_results.csv"
    print("\nRunning the Phase 1 CLI on the same folder for comparison...")
    t_cli_start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-m", "app.pipeline.cli", str(SAMPLE_DIR), "--out", str(cli_csv), "--json", str(cli_json)],
        cwd=BACKEND_DIR,
        check=True,
    )
    cli_elapsed = time.perf_counter() - t_cli_start
    cli_results = {r["filename"]: r for r in json.loads(cli_json.read_text())}
    api_by_name = {r["image_name"]: r for r in records}

    mismatches = []
    compared = 0
    for name, cli_r in cli_results.items():
        api_r = api_by_name.get(name)
        if api_r is None:
            continue
        compared += 1
        if (
            api_r["status"] != cli_r["status"]
            or (api_r["awb"] or None) != (cli_r["awb"] or None)
            or (api_r["primary_flag"] or None) != (cli_r["primary_flag"] or None)
        ):
            mismatches.append(
                {
                    "name": name,
                    "api": {"status": api_r["status"], "awb": api_r["awb"], "flag": api_r["primary_flag"]},
                    "cli": {"status": cli_r["status"], "awb": cli_r["awb"], "flag": cli_r["primary_flag"]},
                }
            )

    print(f"\nCLI run took {cli_elapsed:.1f}s for {len(cli_results)} images.")
    verdict = "IDENTICAL" if not mismatches else f"{len(mismatches)} MISMATCHES"
    print(f"Compared {compared} images (API vs CLI, same files): {verdict}")
    for m in mismatches[:20]:
        print(f"  MISMATCH {m['name']}: api={m['api']} cli={m['cli']}")

    print(f"\nScratch data (export.csv, cli_results.json/csv) left at {SCRATCH_DIR} for inspection.")


if __name__ == "__main__":
    main()
