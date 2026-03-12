"""Tests for the health check endpoint."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root(client):
    resp = client.get("/")
    body = resp.json()
    assert resp.status_code == 200
    assert body["name"] == "IntelliKnow KMS"
    assert "docs" in body
