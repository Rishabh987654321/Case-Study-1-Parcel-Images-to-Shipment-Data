from tests.conftest import make_jpeg_bytes


def test_create_batch(client):
    r = client.post("/api/batches", json={})
    assert r.status_code == 201
    body = r.json()
    assert "batch_id" in body
    assert body["status"] == "created"


def test_create_batch_with_name(client):
    r = client.post("/api/batches", json={"name": "Station 4 morning"})
    assert r.status_code == 201
    batch_id = r.json()["batch_id"]
    r2 = client.get(f"/api/batches/{batch_id}")
    assert r2.json()["name"] == "Station 4 morning"


def test_get_nonexistent_batch(client):
    r = client.get("/api/batches/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BATCH_NOT_FOUND"


def test_finalize_with_zero_images(client):
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    r = client.post(f"/api/batches/{batch_id}/finalize")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_UPLOAD"


def test_finalize_is_idempotent(client):
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    client.post(f"/api/batches/{batch_id}/images", files=[("files", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))])
    r1 = client.post(f"/api/batches/{batch_id}/finalize")
    r2 = client.post(f"/api/batches/{batch_id}/finalize")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["status"] == r2.json()["status"] == "processing"


def test_delete_batch(client):
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    r = client.delete(f"/api/batches/{batch_id}")
    assert r.status_code == 204
    r2 = client.get(f"/api/batches/{batch_id}")
    assert r2.status_code == 404


def test_list_batches_newest_first(client):
    id1 = client.post("/api/batches", json={"name": "first"}).json()["batch_id"]
    id2 = client.post("/api/batches", json={"name": "second"}).json()["batch_id"]
    r = client.get("/api/batches")
    assert r.status_code == 200
    ids = [item["batch_id"] for item in r.json()["items"]]
    assert ids.index(id2) < ids.index(id1)


def test_cancel_is_idempotent(client):
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    r1 = client.post(f"/api/batches/{batch_id}/cancel")
    r2 = client.post(f"/api/batches/{batch_id}/cancel")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == "cancelled"


def test_retry_failed_stub(client):
    batch_id = client.post("/api/batches", json={}).json()["batch_id"]
    r = client.post(f"/api/batches/{batch_id}/retry-failed")
    assert r.status_code == 200
    assert r.json() == {"requeued": 0}
