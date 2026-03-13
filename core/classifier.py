"""Classify queries into intent spaces using embedding similarity (no API call)."""
from __future__ import annotations
import numpy as np
from db.database import get_db_connection
from core.embedder import embed_texts


# Cache intent space embeddings so they are only computed once
_space_embeddings: dict[str, np.ndarray] = {}
_space_cache_key: str = ""  # hash of space names to detect changes


def _get_active_intent_spaces() -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT name, display_name, description, keywords, confidence_threshold
               FROM intent_spaces WHERE is_active = 1"""
        ).fetchall()
    return [dict(r) for r in rows]


def _get_space_embeddings(spaces: list[dict]) -> dict[str, np.ndarray]:
    """Return cached per-space embeddings, rebuilding if spaces changed."""
    global _space_embeddings, _space_cache_key

    cache_key = ",".join(s["name"] for s in spaces)
    if cache_key == _space_cache_key and _space_embeddings:
        return _space_embeddings

    texts = []
    names = []
    for s in spaces:
        # Combine description and keywords for a richer representation
        text = s["description"]
        if s.get("keywords", "").strip():
            text += ". Keywords: " + s["keywords"]
        texts.append(text)
        names.append(s["name"])

    vecs = embed_texts(texts)  # shape (N, dim), already normalised
    _space_embeddings = {name: vecs[i] for i, name in enumerate(names)}
    _space_cache_key = cache_key
    return _space_embeddings


def classify_query(query: str, query_vector: np.ndarray | None = None) -> dict:
    """Return {intent_space, confidence, reasoning} using local embedding similarity.

    Pass query_vector if already computed to avoid re-embedding.
    """
    spaces = _get_active_intent_spaces()
    if not spaces:
        return {"intent_space": "general", "confidence": 0.5, "reasoning": "No intent spaces configured"}

    if query_vector is None:
        from core.embedder import embed_query
        query_vector = embed_query(query)

    q_flat = query_vector.flatten()
    space_embs = _get_space_embeddings(spaces)

    # Cosine similarities (vectors are L2-normalised → dot product = cosine)
    raw_scores = np.array([float(np.dot(q_flat, space_embs[s["name"]])) for s in spaces])

    # Softmax with temperature scaling to sharpen the distribution.
    # Raw cosine similarities cluster in a narrow range (e.g. 0.75–0.85),
    # making plain softmax output near-uniform (~1/N per space).
    # Multiplying by temperature amplifies differences before exponentiation.
    temperature = 10.0
    exp_scores = np.exp((raw_scores - raw_scores.max()) * temperature)
    probs = exp_scores / exp_scores.sum()

    best_idx = int(np.argmax(probs))
    best_space = spaces[best_idx]["name"]
    confidence = float(probs[best_idx])
    cosine_sim = float(raw_scores[best_idx])

    return {
        "intent_space": best_space,
        "confidence": confidence,
        "reasoning": f"Embedding similarity {cosine_sim:.3f} (confidence {confidence:.2f})",
    }
