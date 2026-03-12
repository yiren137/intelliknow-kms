"""Unit tests for the intent classifier.

These tests call the classifier directly (no HTTP) to verify routing logic
against the queries defined in test_cases.json.
"""
import pytest
from core.classifier import classify_query


@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"])
    for c in [
        {"id": "hr-01", "query": "How many vacation days do I get?", "expected_intent_space": "hr"},
        {"id": "hr-02", "query": "What is the parental leave policy?", "expected_intent_space": "hr"},
        {"id": "hr-03", "query": "How does the performance review process work?", "expected_intent_space": "hr"},
        {"id": "hr-04", "query": "What health insurance plans are available?", "expected_intent_space": "hr"},
        {"id": "hr-05", "query": "Can I work from home?", "expected_intent_space": "hr"},
        {"id": "hr-06", "query": "How many sick days am I entitled to?", "expected_intent_space": "hr"},
        {"id": "legal-01", "query": "What is the NDA policy?", "expected_intent_space": "legal"},
        {"id": "legal-02", "query": "Who owns the intellectual property I create at work?", "expected_intent_space": "legal"},
        {"id": "legal-03", "query": "What are the GDPR data retention requirements?", "expected_intent_space": "legal"},
        {"id": "legal-04", "query": "How do I get a contract reviewed?", "expected_intent_space": "legal"},
        {"id": "finance-01", "query": "What is the meal per diem rate for business travel?", "expected_intent_space": "finance"},
        {"id": "finance-02", "query": "How do I submit an expense report?", "expected_intent_space": "finance"},
        {"id": "finance-03", "query": "What class do I fly for international travel?", "expected_intent_space": "finance"},
        {"id": "finance-04", "query": "What is the company's total budget for this year?", "expected_intent_space": "finance"},
        {"id": "general-01", "query": "Where is the company headquartered?", "expected_intent_space": "general"},
        {"id": "general-02", "query": "What are the company's core values?", "expected_intent_space": "general"},
        {"id": "general-03", "query": "What project management tools does the company use?", "expected_intent_space": "general"},
    ]
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


def test_classification_fallback_without_api_key(monkeypatch):
    from config import settings as s
    original = s.get_settings()
    monkeypatch.setattr(original, "gemini_api_key", "")
    result = classify_query("What is the vacation policy?")
    assert result["intent_space"] == "general"
    assert result["confidence"] == 0.5
