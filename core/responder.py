"""Use Gemini to generate a cited answer from retrieved chunks."""
from __future__ import annotations
import logging
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
_model = None


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
    return _model


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_gemini(model, prompt: str) -> str:
    response = model.generate_content(prompt)
    return response.text.strip()


def generate_response(
    query: str,
    chunks: list[dict],
    intent_space: str,
    conversation_history: list[tuple[str, str]] | None = None,
) -> str:
    """Generate a cited answer.

    chunks: list of dicts with keys: chunk_text, document_id, chunk_id
    conversation_history: list of (user_query, assistant_answer) tuples (oldest first)
    Returns the answer string.
    """
    if not chunks:
        return (
            "I couldn't find any relevant documents in the knowledge base to answer your question. "
            "Please try rephrasing, or upload relevant documents first."
        )

    if not settings.gemini_api_key:
        top = chunks[0]
        return f"[No API key] Closest match:\n\n{top['chunk_text']}"

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Source {i}]\n{chunk['chunk_text']}")
    context = "\n\n---\n\n".join(context_parts)

    history_section = ""
    if conversation_history:
        history_lines = []
        for user_q, assistant_a in conversation_history:
            history_lines.append(f"User: {user_q}")
            history_lines.append(f"Assistant: {assistant_a}")
        history_section = "\n\nPrevious conversation:\n" + "\n".join(history_lines) + "\n"

    prompt = f"""You are a knowledgeable assistant for a company knowledge management system.
Use ONLY the provided context below to answer the user's question.
If the context does not contain enough information, say so honestly.
Cite your sources using [Source N] notation inline.

Intent space: {intent_space}{history_section}

Context:
{context}

Current question: {query}

Answer:"""

    try:
        model = _get_model()
        return _call_gemini(model, prompt)
    except Exception as e:
        logger.error("Gemini generation failed after retries: %s", e)
        return f"Error generating response: {str(e)[:200]}"
