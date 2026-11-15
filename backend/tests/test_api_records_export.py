from datetime import UTC, datetime

from tests.conftest import make_jpeg_bytes


def _new_batch(client) -> str:
    return client.post("/api/batches", json={}).json()["batch_id"]


def _seed_result(client, image_id: str, **overrides) -> None:
    """Insert a Result row directly - there is no Phase 3 worker yet to produce one."""
    from app.models import Result

    defaults = {
        "image_id": image_id, "status": "OK", "primary_flag": None, "flag_reason": None, "warnings": "[]",
        "awb": "19109110324413", "awb_suggestion": None, "awb_source": "overlay", "awb_confidence": 0.8,
        "weight_kg": 1.5, "weight_raw": "1.5 kg", "length_cm": 10.0, "width_cm": 20.0, "height_cm": 5.0,
        "dimensions_raw": "10x20x5", "courier": "Delhivery", "confidence": 0.8, "evidence": "{}",
        "pipeline_version": "1.0.0", "processing_ms": 100, "processed_at": datetime.now(UTC).isoformat(),
    }
    defaults.update(overrides)
    db = client.SessionLocal()
    db.add(Result(**defaults))
    db.commit()
    db.close()


def test_records_for_empty_batch(client):
    batch_id = _new_batch(client)
    r = client.get(f"/api/batches/{batch_id}/records")
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_records_show_pending_before_processing(client):
    batch_id = _new_batch(client)
    client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    r = client.get(f"/api/batches/{batch_id}/records")
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "PENDING"


def test_export_csv_not_ready_before_processing(client):
    batch_id = _new_batch(client)
    client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    r = client.get(f"/api/batches/{batch_id}/export.csv")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "BATCH_NOT_READY"


def test_export_csv_unknown_batch(client):
    r = client.get("/api/batches/does-not-exist/export.csv")
    assert r.status_code == 404


def test_get_record_detail_not_found(client):
    batch_id = _new_batch(client)
    r = client.get(f"/api/batches/{batch_id}/records/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "IMAGE_NOT_FOUND"


def test_thumbnail_and_original_served(client):
    batch_id = _new_batch(client)
    accepted = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))]).json()["accepted"]
    image_id = accepted[0]["image_id"]

    thumb = client.get(f"/api/images/{image_id}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"

    original = client.get(f"/api/images/{image_id}/original")
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/jpeg"


def test_thumbnail_not_found(client):
    r = client.get("/api/images/does-not-exist/thumbnail")
    assert r.status_code == 404


def test_export_csv_has_bom_and_headers(client):
    batch_id = _new_batch(client)
    accepted = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))]).json()["accepted"]
    _seed_result(client, accepted[0]["image_id"])

    r = client.get(f"/api/batches/{batch_id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    raw = r.content
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header.split(",") == [
        "image_name", "status", "primary_flag", "flag_reason", "awb", "awb_suggestion",
        "awb_source", "awb_confidence", "weight_kg", "weight_raw", "length_cm", "width_cm",
        "height_cm", "dimensions_raw", "warnings", "processed_at", "pipeline_version", "image_id",
    ]
    assert "a.jpg" in text and "19109110324413" in text


def test_export_csv_formula_injection_guard(client):
    batch_id = _new_batch(client)
    accepted = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))]).json()["accepted"]
    _seed_result(client, accepted[0]["image_id"], awb_suggestion="=cmd|'/c calc'!A1")

    r = client.get(f"/api/batches/{batch_id}/export.csv")
    text = r.content.decode("utf-8-sig")
    assert "'=cmd" in text


def test_export_csv_only_ok_filter(client):
    batch_id = _new_batch(client)
    accepted = client.post(
        f"/api/batches/{batch_id}/images",
        files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg")), ("files", ("b.jpg", make_jpeg_bytes(500, 500), "image/jpeg"))],
    ).json()["accepted"]
    _seed_result(client, accepted[0]["image_id"], status="OK")
    _seed_result(client, accepted[1]["image_id"], status="FLAGGED", primary_flag="NO_PARCEL", flag_reason="empty frame", awb=None)

    r = client.get(f"/api/batches/{batch_id}/export.csv?only=ok")
    lines = r.content.decode("utf-8-sig").splitlines()
    assert len(lines) == 2  # header + 1 OK row
    assert "a.jpg" in lines[1]


def test_annotated_stub_returns_404(client):
    batch_id = _new_batch(client)
    accepted = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))]).json()["accepted"]
    image_id = accepted[0]["image_id"]
    r = client.get(f"/api/images/{image_id}/annotated")
    assert r.status_code == 404
