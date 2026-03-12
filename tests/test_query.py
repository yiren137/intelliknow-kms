"""Tests for the /api/v1/query endpoint.

E2E tests that go through the full pipeline:
  classify → embed → vector search → generate response

Documents must be uploaded before running these tests.
Run test_documents.py first, or upload via the API manually.
"""
import pytest


QUERY_ENDPOINT = "/api/v1/query"


# ── Schema & validation ───────────────────────────────────────────────────

def test_query_empty_string_returns_422(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": ""})
    assert resp.status_code == 422


def test_query_response_schema(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What is the vacation policy?", "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    for field in ["query", "intent_space", "intent_space_name", "confidence", "reasoning", "answer", "sources", "latency_ms", "status"]:
        assert field in body, f"Missing field: {field}"


def test_query_status_is_success(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What is the sick leave policy?"})
    assert resp.json()["status"] == "success"


def test_query_latency_is_positive(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What are the core company values?"})
    assert resp.json()["latency_ms"] > 0


def test_query_confidence_range(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What is the NDA policy?"})
    confidence = resp.json()["confidence"]
    assert 0.0 <= confidence <= 1.0


# ── HR queries ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,keywords", [
    ("How many vacation days do I get?", ["vacation", "days"]),
    ("What is the parental leave policy?", ["parental", "leave"]),
    ("What health benefits does the company offer?", ["medical", "health"]),
    ("Can I work remotely?", ["remote"]),
    ("How many sick days do I get?", ["sick"]),
    ("What happens during a performance review?", ["review", "performance"]),
    ("What is the severance policy?", ["severance", "termination"]),
])
def test_hr_query_routed_correctly(client, query, keywords):
    resp = client.post(QUERY_ENDPOINT, json={"query": query, "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent_space"] == "hr", (
        f"Expected 'hr', got '{body['intent_space']}'. Query: '{query}'"
    )
    answer_lower = body["answer"].lower()
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    assert matched, f"None of {keywords} found in answer for '{query}':\n{body['answer']}"


# ── Legal queries ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,keywords", [
    ("What is the NDA policy?", ["nda", "non-disclosure", "confidential"]),
    ("Who owns intellectual property created at work?", ["intellectual property", "acme", "company"]),
    ("What are the GDPR requirements?", ["gdpr", "data"]),
    ("How do I submit a contract for review?", ["contract", "legal"]),
    ("What is the anti-bribery policy?", ["bribery", "gift"]),
])
def test_legal_query_routed_correctly(client, query, keywords):
    resp = client.post(QUERY_ENDPOINT, json={"query": query, "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent_space"] == "legal", (
        f"Expected 'legal', got '{body['intent_space']}'. Query: '{query}'"
    )
    answer_lower = body["answer"].lower()
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    assert matched, f"None of {keywords} found in answer for '{query}':\n{body['answer']}"


# ── Finance queries ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query,keywords", [
    ("What is the meal per diem for travel?", ["meal", "per diem"]),
    ("How do I book business travel?", ["travel", "concur"]),
    ("What is the budget approval process?", ["budget", "approval"]),
    ("What is the corporate credit card limit?", ["credit", "limit"]),
    ("How quickly are expenses reimbursed?", ["reimburs", "10 business days"]),
])
def test_finance_query_routed_correctly(client, query, keywords):
    resp = client.post(QUERY_ENDPOINT, json={"query": query, "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent_space"] == "finance", (
        f"Expected 'finance', got '{body['intent_space']}'. Query: '{query}'"
    )
    answer_lower = body["answer"].lower()
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    assert matched, f"None of {keywords} found in answer for '{query}':\n{body['answer']}"


# ── General queries ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query,keywords", [
    ("Where is the company headquartered?", ["san francisco"]),
    ("What are the company values?", ["customer", "values"]),
    ("What tools does the company use?", ["jira", "asana", "slack"]),
    ("How much is the L&D budget?", ["1,500", "learning"]),
    ("When is the all-hands meeting?", ["thursday", "all-hands"]),
])
def test_general_query_routed_correctly(client, query, keywords):
    resp = client.post(QUERY_ENDPOINT, json={"query": query, "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent_space"] == "general", (
        f"Expected 'general', got '{body['intent_space']}'. Query: '{query}'"
    )
    answer_lower = body["answer"].lower()
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    assert matched, f"None of {keywords} found in answer for '{query}':\n{body['answer']}"


# ── Edge cases ────────────────────────────────────────────────────────────

def test_query_with_no_matching_docs_returns_graceful_message(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What is the policy on adopting office pets?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    # Answer should not be empty even if no strong match
    assert len(body["answer"]) > 10


def test_query_sources_list_structure(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "What is the vacation policy?"})
    sources = resp.json()["sources"]
    assert isinstance(sources, list)
    for source in sources:
        assert "document_name" in source
        assert "score" in source
        assert isinstance(source["score"], float)


def test_query_logs_source_field(client):
    resp = client.post(QUERY_ENDPOINT, json={"query": "Tell me about sick leave.", "source": "test_runner"})
    assert resp.status_code == 200
    # Verify it appears in query logs
    logs = client.get("/api/v1/analytics/queries?limit=5").json()
    sources = [l["source"] for l in logs]
    assert "test_runner" in sources
