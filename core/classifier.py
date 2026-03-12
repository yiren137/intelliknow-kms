"""Use Gemini to classify a query into an intent space."""
from __future__ import annotations
import json
import google.generativeai as genai
from config.settings import get_settings
from db.database import get_db_connection

settings = get_settings()
_model = None


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
    return _model


def _get_active_intent_spaces() -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT name, display_name, description, keywords, confidence_threshold
               FROM intent_spaces WHERE is_active = 1"""
        ).fetchall()
    return [dict(r) for r in rows]


def classify_query(query: str) -> dict:
    """Return {intent_space, confidence, reasoning}.

    Falls back to 'general' if Gemini is unavailable or API key missing.
    """
    if not settings.gemini_api_key:
        return {"intent_space": "general", "confidence": 0.5, "reasoning": "No API key configured"}

    spaces = _get_active_intent_spaces()
    if not spaces:
        return {"intent_space": "general", "confidence": 0.5, "reasoning": "No intent spaces configured"}

    spaces_desc_parts = []
    for s in spaces:
        line = f"- {s['name']}: {s['display_name']} — {s['description']}"
        if s.get("keywords", "").strip():
            line += f" (keywords: {s['keywords']})"
        spaces_desc_parts.append(line)
    spaces_desc = "\n".join(spaces_desc_parts)

    prompt = f"""You are a query classifier for a knowledge management system.
Given a user query, classify it into exactly one of the following intent spaces:

{spaces_desc}

Respond ONLY with valid JSON in this exact format:
{{
  "intent_space": "<one of the space names above>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence explanation>"
}}

User query: {query}"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        content = response.text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        valid_names = {s["name"] for s in spaces}
        if result.get("intent_space") not in valid_names:
            result["intent_space"] = "general"
        return result
    except Exception as e:
        return {
            "intent_space": "general",
            "confidence": 0.3,
            "reasoning": f"Classification failed: {str(e)[:100]}",
        }
