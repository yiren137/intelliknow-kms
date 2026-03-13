"""Cross-encoder reranker for improving retrieval precision."""
from __future__ import annotations
from sentence_transformers import CrossEncoder
from config.settings import get_settings

settings = get_settings()

_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(settings.reranker_model)
    return _reranker


def rerank(query: str, chunks: list[dict], top_k: int | None = None) -> list[dict]:
    """Re-score chunks using a cross-encoder and return sorted by relevance.

    chunks: list of dicts with at least 'chunk_text' key.
    top_k: if provided, return only the top_k results.
    """
    if not chunks:
        return chunks

    reranker = _get_reranker()
    pairs = [(query, c["chunk_text"]) for c in chunks]
    scores = reranker.predict(pairs)

    scored = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    result = [c for _, c in scored]

    if top_k is not None:
        result = result[:top_k]

    return result
