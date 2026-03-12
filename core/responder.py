"""Use Gemini to generate a cited answer from retrieved chunks."""
from __future__ import annotations
import google.generativeai as genai
from config.settings import get_settings

settings = get_settings()
_model = None


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
    return _model


def generate_response(query: str, chunks: list[dict], intent_space: str) -> str:
    """Generate a cited answer.

    chunks: list of dicts with keys: chunk_text, document_id, chunk_id
    Returns the answer string.
    """
    if not chunks:
        return (
            "I couldn't find relevant information in the knowledge base to answer your query. "
            "Please try rephrasing your question or upload relevant documents."
        )

    if not settings.gemini_api_key:
        # Fallback: return top chunk text directly
        top = chunks[0]
        return f"[No API key] Closest match:\n\n{top['chunk_text']}"

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Source {i}]\n{chunk['chunk_text']}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""You are a knowledgeable assistant for a company knowledge management system.
Use ONLY the provided context below to answer the user's question.
If the context does not contain enough information, say so honestly.
Cite your sources using [Source N] notation inline.

Intent space: {intent_space}

Context:
{context}

User question: {query}

Answer:"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error generating response: {str(e)[:200]}"
