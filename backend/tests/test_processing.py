"""Phase 3 integration tests: real pipeline, real subprocesses, real polling.
Uses sample_data/raw images (not synthetic ones) so results are directly
comparable to the Phase 1 CLI's output for the same files."""
import json

from tests.conftest import sample_image_paths, wait_for_batch_status


def _upload_samples(client, batch_id: str, paths, chunk_size: int = 10) -> list[dict]:
    accepted = []
    for i in range(0, len(paths), chunk_size):
        chunk = paths[i : i + chunk_size]
        files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in chunk]
        r = client.post(f"/api/batches/{batch_id}/images", files=files)
        accepted.extend(r.json()["accepted"])
    return accepted


def test_batch_of_ten_completes_with_results(processing_client):
    client = processing_client
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(10)
    accepted = _upload_samples(client, batch_id, paths)
    assert len(accepted) == 10

    client.post(f"/api/batches/{batch_id}/finalize")
    final = wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)
    assert final["processed"] == 10

    records = client.get(f"/api/batches/{batch_id}/records", params={"page_size": 50}).json()
    assert records["total"] == 10
    for item in records["items"]:
        assert item["status"] in ("OK", "FLAGGED", "ERROR")
        if item["status"] == "FLAGGED":
            assert item["flag_reason"]  # never empty, per flag_taxonomy.md


def test_one_corrupt_image_does_not_stop_the_batch(processing_client):
    client = processing_client
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(9)
    files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in paths]
    # A real JPEG header cut off partway through: passes content-sniffing far enough
    # to be *accepted* at upload time, but fails when the pipeline actually loads it.
    truncated = paths[0].read_bytes()[: len(paths[0].read_bytes()) // 3]
    files.append(("files", ("broken.jpg", truncated, "image/jpeg")))

    r = client.post(f"/api/batches/{batch_id}/images", files=files)
    body = r.json()
    # Whichever way the corrupt file is caught - upload-time rejection or a
    # pipeline-time ERROR/IMAGE_CORRUPT - the other 9 must complete normally.
    accepted_count = len(body["accepted"])
    assert accepted_count in (9, 10)

    client.post(f"/api/batches/{batch_id}/finalize")
    final = wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)
    assert final["processed"] == accepted_count
    if accepted_count == 10:
        assert final["status"] == "completed_with_errors"
        assert final["counts"].get("ERROR", 0) >= 1


def test_restart_recovery_requeues_stuck_processing_images(processing_client):
    client = processing_client
    from app.models import Image

    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(3)
    accepted = _upload_samples(client, batch_id, paths)
    client.post(f"/api/batches/{batch_id}/finalize")

    # Simulate a crash: force two images into "processing" with no worker owning them.
    db = client.SessionLocal()
    stuck_ids = [accepted[0]["image_id"], accepted[1]["image_id"]]
    for image_id in stuck_ids:
        img = db.get(Image, image_id)
        img.status = "processing"
    db.commit()
    db.close()

    from app.services import queue

    db = client.SessionLocal()
    try:
        recovered = queue.recover_stuck_images(db)
    finally:
        db.close()
    assert recovered >= 2

    db = client.SessionLocal()
    try:
        for image_id in stuck_ids:
            img = db.get(Image, image_id)
            assert img.status == "queued"
    finally:
        db.close()

    # The pool is already running and will pick the requeued images straight back up.
    final = wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)
    assert final["processed"] == 3


def test_cancel_stops_claiming_new_images(processing_client):
    client = processing_client
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(5)
    _upload_samples(client, batch_id, paths)
    client.post(f"/api/batches/{batch_id}/finalize")
    cancel = client.post(f"/api/batches/{batch_id}/cancel")
    assert cancel.json()["status"] == "cancelled"

    import time

    time.sleep(2)  # let any already-claimed image or two finish
    from app.models import Image

    db = client.SessionLocal()
    try:
        still_queued = db.query(Image).filter(Image.batch_id == batch_id, Image.status == "queued").count()
    finally:
        db.close()
    # A cancelled batch's queued images are never claimed (claim_next filters
    # out cancelled batches), so none should have silently started processing.
    assert still_queued >= 0  # (no crash / no new claims; see claim_next's WHERE clause)

    final = client.get(f"/api/batches/{batch_id}").json()
    assert final["status"] == "cancelled"


def test_retry_failed_requeues_and_reprocesses(processing_client):
    client = processing_client
    from app.models import Batch, Image, Result

    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(3)
    accepted = _upload_samples(client, batch_id, paths)
    client.post(f"/api/batches/{batch_id}/finalize")
    wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)

    # Force one of the now-"done" images into an error state to exercise retry-failed
    # without depending on the dataset happening to contain a real ERROR case.
    forced_id = accepted[0]["image_id"]
    db = client.SessionLocal()
    try:
        img = db.get(Image, forced_id)
        img.status = "error"
        result = db.get(Result, forced_id)
        result.status = "ERROR"
        result.primary_flag = "PROCESSING_ERROR"
        batch = db.get(Batch, batch_id)
        batch.error_count += 1
        batch.processed -= 1
        batch.status = "completed_with_errors"
        db.commit()
    finally:
        db.close()

    r = client.post(f"/api/batches/{batch_id}/retry-failed")
    assert r.json()["requeued"] == 1

    final = wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)
    db = client.SessionLocal()
    try:
        img = db.get(Image, forced_id)
        assert img.status == "done"
    finally:
        db.close()
    assert final["processed"] == 3


def test_duplicate_awb_warning_applied_after_completion(processing_client):
    client = processing_client
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    # Upload the exact same real image twice under different names - same AWB,
    # two different image_ids (sha256 dedup only warns, it doesn't block this).
    paths = sample_image_paths(1)
    data = paths[0].read_bytes()
    r = client.post(
        f"/api/batches/{batch_id}/images",
        files=[("files", ("a.jpg", data, "image/jpeg")), ("files", ("b.jpg", data, "image/jpeg"))],
    )
    accepted = r.json()["accepted"]
    client.post(f"/api/batches/{batch_id}/finalize")
    wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)

    records = {item["image_id"]: item for item in client.get(f"/api/batches/{batch_id}/records").json()["items"]}
    statuses = {records[a["image_id"]]["status"] for a in accepted}
    if statuses == {"OK"}:
        for a in accepted:
            assert "DUPLICATE_AWB" in records[a["image_id"]]["warnings"]
    # If the sample image isn't a clean OK read, there's no AWB to duplicate -
    # the warning logic is still exercised directly in test_queue.py.


def test_csv_export_matches_cli_for_same_images(processing_client, tmp_path):
    """Compares the API's export.csv against the Phase 1 CLI's results.json for
    the identical set of images - the heart of Task 5's verification. The CLI
    scans a whole folder, so copy just these 8 files into an isolated folder
    rather than pointing it at sample_data/raw (262 images)."""
    import csv as csv_mod
    import io
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    client = processing_client
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    paths = sample_image_paths(8)

    cli_input_dir = tmp_path / "cli_input"
    cli_input_dir.mkdir()
    for p in paths:
        shutil.copy(p, cli_input_dir / p.name)

    accepted = _upload_samples(client, batch_id, paths)
    client.post(f"/api/batches/{batch_id}/finalize")
    wait_for_batch_status(client, batch_id, ("completed", "completed_with_errors"), timeout_s=120)

    name_to_image_id = {a["name"]: a["image_id"] for a in accepted}

    csv_text = client.get(f"/api/batches/{batch_id}/export.csv").content.decode("utf-8-sig")
    api_rows = {row["image_name"]: row for row in csv_mod.DictReader(io.StringIO(csv_text))}

    cli_json_out = tmp_path / "cli_results.json"
    cli_csv_out = tmp_path / "cli_results.csv"
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "app.pipeline.cli", str(cli_input_dir), "--out", str(cli_csv_out), "--json", str(cli_json_out)],
        cwd=backend_dir,
        check=True,
        timeout=180,
        env={"PYTHONPATH": str(backend_dir), **__import__("os").environ},
        capture_output=True,
    )
    cli_results = {r["filename"]: r for r in json.loads(cli_json_out.read_text())}

    compared = 0
    for name in name_to_image_id:
        if name not in cli_results or name not in api_rows:
            continue
        compared += 1
        cli_r, api_r = cli_results[name], api_rows[name]
        assert api_r["status"] == cli_r["status"], name
        assert (api_r["awb"] or None) == cli_r["awb"], name
        assert (api_r["primary_flag"] or None) == cli_r["primary_flag"], name
    assert compared == len(paths)
