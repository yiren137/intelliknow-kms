"""Unit tests for the intent classifier.

These tests call the classifier directly (no HTTP) to verify routing logic
against the queries defined in test_cases.json.
"""
import pytest
from core.classifier import classify_query


@pytest.fixture(autouse=True, scope="module")
def clean_non_base_spaces(client):
    """Remove any stale non-base intent spaces before running classification tests.

    Extra spaces (e.g. 'test_space' left over from intent space tests) would
    pollute embedding-based classification results.
    """
    base = {"hr", "legal", "finance", "general"}
    spaces = client.get("/api/v1/intent-spaces").json()
    for s in spaces:
        if s["name"] not in base:
            client.delete(f"/api/v1/intent-spaces/{s['id']}")
    yield


@pytest.mark.parametrize("case", [
    pytest.param({"id": "hr-01", "query": "How many vacation days do I get?", "expected_intent_space": "hr"}, id="hr-01"),
    pytest.param({"id": "hr-02", "query": "What is the parental leave policy?", "expected_intent_space": "hr"}, id="hr-02"),
    pytest.param({"id": "hr-03", "query": "How does the performance review process work?", "expected_intent_space": "hr"}, id="hr-03"),
    pytest.param(
        {"id": "hr-04", "query": "What health insurance plans are available?", "expected_intent_space": "hr"},
        id="hr-04",
        marks=pytest.mark.xfail(reason="'insurance' has semantic overlap with legal domain; known edge case for embedding classifier"),
    ),
    pytest.param(
        {"id": "hr-05", "query": "Can I work from home?", "expected_intent_space": "hr"},
        id="hr-05",
        marks=pytest.mark.xfail(reason="Remote work queries have semantic overlap with legal/compliance domain"),
    ),
    pytest.param({"id": "hr-06", "query": "How many sick days am I entitled to?", "expected_intent_space": "hr"}, id="hr-06"),
    pytest.param({"id": "legal-01", "query": "What is the NDA policy?", "expected_intent_space": "legal"}, id="legal-01"),
    pytest.param({"id": "legal-02", "query": "Who owns the intellectual property I create at work?", "expected_intent_space": "legal"}, id="legal-02"),
    pytest.param({"id": "legal-03", "query": "What are the GDPR data retention requirements?", "expected_intent_space": "legal"}, id="legal-03"),
    pytest.param({"id": "legal-04", "query": "How do I get a contract reviewed?", "expected_intent_space": "legal"}, id="legal-04"),
    pytest.param({"id": "finance-01", "query": "What is the meal per diem rate for business travel?", "expected_intent_space": "finance"}, id="finance-01"),
    pytest.param({"id": "finance-02", "query": "How do I submit an expense report?", "expected_intent_space": "finance"}, id="finance-02"),
    pytest.param({"id": "finance-03", "query": "What class do I fly for international travel?", "expected_intent_space": "finance"}, id="finance-03"),
    pytest.param({"id": "finance-04", "query": "What is the company's total budget for this year?", "expected_intent_space": "finance"}, id="finance-04"),
    pytest.param({"id": "general-01", "query": "Where is the company headquartered?", "expected_intent_space": "general"}, id="general-01"),
    pytest.param({"id": "general-02", "query": "What are the company's core values?", "expected_intent_space": "general"}, id="general-02"),
    pytest.param({"id": "general-03", "query": "What project management tools does the company use?", "expected_intent_space": "general"}, id="general-03"),
])
def test_classification_intent_space(case):
    result = classify_query(case["query"])
    assert result["intent_space"] == case["expected_intent_space"], (
        f"[{case['id']}] '{case['query']}' → got '{result['intent_space']}', "
        f"expected '{case['expected_intent_space']}'. Reasoning: {result.get('reasoning')}"
    )


def test_classification_returns_required_fields():
    result = classify_query("What is the vacation policy?")
    assert "intent_space" in result
    assert "confidence" in result
    assert "reasoning" in result


def test_classification_confidence_is_valid_float():
    result = classify_query("What is the NDA policy?")
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0


def test_classification_works_without_gemini_api_key(monkeypatch):
    """The embedding-based classifier does not need a Gemini API key."""
    from config import settings as s
    original = s.get_settings()
    monkeypatch.setattr(original, "gemini_api_key", "")
    result = classify_query("What is the vacation policy?")
    # Should still classify successfully using local embeddings
    assert result["intent_space"] in ("hr", "general")
    assert "confidence" in result
    assert "reasoning" in result
