def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert "limits" in body and "providers" in body
    assert body["limits"]["max_files_per_batch"] == 1000
    assert "image/jpeg" in body["limits"]["allowed_types"]
