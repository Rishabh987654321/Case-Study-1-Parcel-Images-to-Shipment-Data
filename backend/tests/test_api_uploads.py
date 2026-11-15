from tests.conftest import make_jpeg_bytes, make_png_bytes


def _new_batch(client) -> str:
    return client.post("/api/batches", json={}).json()["batch_id"]


def test_empty_upload_no_files(client):
    batch_id = _new_batch(client)
    r = client.post(f"/api/batches/{batch_id}/images", files=[])
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_UPLOAD"


def test_txt_renamed_to_jpg_rejected(client):
    batch_id = _new_batch(client)
    r = client.post(
        f"/api/batches/{batch_id}/images",
        files=[("files", ("notes.jpg", b"just some plain text, not an image", "image/jpeg"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["code"] == "NOT_AN_IMAGE"
    assert "notes.jpg" in body["rejected"][0]["message"]


def test_truncated_jpeg_rejected_as_corrupt(client):
    batch_id = _new_batch(client)
    truncated = make_jpeg_bytes()[:200]  # cut off mid-stream
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("broken.jpg", truncated, "image/jpeg"))])
    body = r.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["code"] in ("NOT_AN_IMAGE", "CORRUPT_IMAGE")


def test_file_too_large_rejected(client, monkeypatch):
    from app.services import storage

    monkeypatch.setattr(storage, "MAX_FILE_MB", 0.001)  # ~1KB cap
    batch_id = _new_batch(client)
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("big.jpg", make_jpeg_bytes(800, 800), "image/jpeg"))])
    body = r.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["code"] == "FILE_TOO_LARGE"


def test_1x1_pixel_image_rejected_as_too_small(client):
    batch_id = _new_batch(client)
    tiny = make_jpeg_bytes(1, 1)
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("tiny.jpg", tiny, "image/jpeg"))])
    body = r.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["code"] == "IMAGE_TOO_SMALL"


def test_valid_png_accepted(client):
    batch_id = _new_batch(client)
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("photo.png", make_png_bytes(), "image/png"))])
    body = r.json()
    assert body["rejected"] == []
    assert len(body["accepted"]) == 1
    assert body["accepted"][0]["name"] == "photo.png"


def test_mixed_valid_and_invalid_in_one_request(client):
    batch_id = _new_batch(client)
    r = client.post(
        f"/api/batches/{batch_id}/images",
        files=[
            ("files", ("good.jpg", make_jpeg_bytes(), "image/jpeg")),
            ("files", ("bad.jpg", b"not an image", "image/jpeg")),
        ],
    )
    body = r.json()
    assert len(body["accepted"]) == 1
    assert len(body["rejected"]) == 1


def test_request_too_large_rejected_before_parsing(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "MAX_REQUEST_MB", 0.0001)
    batch_id = _new_batch(client)
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_upload_to_nonexistent_batch(client):
    r = client.post("/api/batches/does-not-exist/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BATCH_NOT_FOUND"


def test_upload_after_finalize_rejected(client):
    batch_id = _new_batch(client)
    client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    client.post(f"/api/batches/{batch_id}/finalize")
    r = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("b.jpg", make_jpeg_bytes(), "image/jpeg"))])
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BATCH_FINALIZED"


def test_duplicate_file_in_same_batch_gets_warning(client):
    batch_id = _new_batch(client)
    data = make_jpeg_bytes()
    r1 = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", data, "image/jpeg"))])
    r2 = client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a_copy.jpg", data, "image/jpeg"))])
    assert r1.json()["accepted"][0]["warnings"] == []
    assert r2.json()["accepted"][0]["warnings"] == ["DUPLICATE_IMAGE"]
    assert r1.json()["accepted"][0]["image_id"] != r2.json()["accepted"][0]["image_id"]
