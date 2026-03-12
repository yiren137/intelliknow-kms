"""Tests for analytics endpoints."""


def test_analytics_summary_schema(client):
    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    for field in ["total_queries", "successful_queries", "success_rate", "total_documents", "total_chunks", "avg_latency_ms", "top_intent_spaces"]:
        assert field in body, f"Missing field: {field}"


def test_analytics_summary_success_rate_range(client):
    body = client.get("/api/v1/analytics/summary").json()
    assert 0.0 <= body["success_rate"] <= 1.0


def test_analytics_summary_counts_non_negative(client):
    body = client.get("/api/v1/analytics/summary").json()
    assert body["total_queries"] >= 0
    assert body["successful_queries"] >= 0
    assert body["total_documents"] >= 0
    assert body["total_chunks"] >= 0


def test_analytics_queries_returns_list(client):
    resp = client.get("/api/v1/analytics/queries")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_queries_schema(client):
    # Run a query first to ensure there's at least one log entry
    client.post("/api/v1/query", json={"query": "What is the vacation policy?", "source": "analytics_test"})
    resp = client.get("/api/v1/analytics/queries?limit=1")
    entries = resp.json()
    assert len(entries) >= 1
    entry = entries[0]
    for field in ["id", "query_text", "source", "response_status", "created_at"]:
        assert field in entry


def test_analytics_queries_limit(client):
    resp = client.get("/api/v1/analytics/queries?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) <= 3


def test_analytics_queries_filter_by_source(client):
    source = "unique_test_source_xyz"
    client.post("/api/v1/query", json={"query": "What is the NDA policy?", "source": source})
    resp = client.get(f"/api/v1/analytics/queries?source={source}")
    entries = resp.json()
    assert all(e["source"] == source for e in entries)


def test_analytics_documents_returns_list(client):
    resp = client.get("/api/v1/analytics/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_documents_schema(client):
    resp = client.get("/api/v1/analytics/documents")
    docs = resp.json()
    if docs:
        for field in ["document_id", "original_name", "access_count", "intent_space_name"]:
            assert field in docs[0]


def test_analytics_daily_default(client):
    resp = client.get("/api/v1/analytics/daily")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_daily_custom_range(client):
    resp = client.get("/api/v1/analytics/daily?days=7")
    assert resp.status_code == 200


def test_analytics_daily_max_range(client):
    resp = client.get("/api/v1/analytics/daily?days=365")
    assert resp.status_code == 200


def test_analytics_daily_schema(client):
    # Seed a query so there's at least one day entry
    client.post("/api/v1/query", json={"query": "What are the core values?", "source": "test"})
    resp = client.get("/api/v1/analytics/daily?days=1")
    entries = resp.json()
    if entries:
        assert "date" in entries[0]
        assert "query_count" in entries[0]
