"""Full query pipeline: embed → classify → hybrid search → rerank → respond → log."""
from __future__ import annotations
import json
import logging
import threading
import time
from typing import Optional

from config.settings import get_settings
from db.database import get_db_connection
from core.embedder import embed_query
from core.vector_store import get_vector_store
from core.classifier import classify_query
from core.responder import generate_response
from core.reranker import rerank

settings = get_settings()
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Query result cache                                                    #
# ------------------------------------------------------------------ #
_cache: dict[str, tuple[float, dict]] = {}  # query -> (timestamp, result)
_cache_lock = threading.Lock()


def _get_cached(query: str) -> dict | None:
    if settings.query_cache_ttl <= 0:
        return None
    with _cache_lock:
        entry = _cache.get(query)
        if entry:
            ts, result = entry
            if time.time() - ts < settings.query_cache_ttl:
                return result
            del _cache[query]
    return None


def _set_cache(query: str, result: dict):
    if settings.query_cache_ttl <= 0:
        return
    with _cache_lock:
        _cache[query] = (time.time(), result)


def clear_cache():
    """Clear the query result cache (useful for tests)."""
    with _cache_lock:
        _cache.clear()


# ------------------------------------------------------------------ #
# Helpers                                                               #
# ------------------------------------------------------------------ #

def _get_confidence_threshold(intent_space: str) -> float:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT confidence_threshold FROM intent_spaces WHERE name = ?",
            (intent_space,),
        ).fetchone()
    if row and row["confidence_threshold"] is not None:
        return float(row["confidence_threshold"])
    return 0.7


# ------------------------------------------------------------------ #
# Main pipeline                                                         #
# ------------------------------------------------------------------ #

def run_query(
    query: str,
    source: str = "api",
    user_id: Optional[str] = None,
    conversation_history: Optional[list[tuple[str, str]]] = None,
) -> dict:
    """Execute the full query pipeline and return a result dict."""
    t_start = time.monotonic()

    # Cache lookup (only when no conversation history, since history changes the answer)
    if not conversation_history:
        cached = _get_cached(query)
        if cached:
            logger.info("Cache hit for query: '%s'", query[:60])
            latency_ms = max(1, round((time.monotonic() - t_start) * 1000))
            with get_db_connection() as conn:
                conn.execute(
                    """INSERT INTO query_logs
                       (query_text, source, user_id, intent_space_id, intent_space_name,
                        confidence_score, response_status, response_text, latency_ms,
                        documents_accessed, cache_hit)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        query, source, user_id,
                        cached.get("intent_space_id"), cached.get("intent_space_name"),
                        cached.get("confidence"), "success", cached.get("answer"),
                        latency_ms, "[]",
                    ),
                )
            return {**cached, "latency_ms": latency_ms}

    # 1. Embed query (used for both classification and vector search)
    q_vec = embed_query(query)

    # 2. Classify intent using embedding similarity (local, no API call)
    classification = classify_query(query, query_vector=q_vec)
    intent_space = classification["intent_space"]
    confidence = classification.get("confidence", 0.5)
    reasoning = classification.get("reasoning", "")

    # 3. Apply confidence threshold — fall back to 'general' if below threshold
    threshold = _get_confidence_threshold(intent_space)
    if confidence < threshold and intent_space != "general":
        reasoning = (
            f"Confidence {confidence:.2f} below threshold {threshold:.2f} for '{intent_space}'; "
            f"falling back to 'general'. Original: {reasoning}"
        )
        intent_space = "general"

    # 4. Hybrid search (BM25 + vector with RRF)
    store = get_vector_store(intent_space)
    raw_results = store.hybrid_search(query, q_vec, top_k=settings.max_retrieval_chunks * 2)

    # 5. Filter by minimum score threshold
    raw_results = [(score, meta) for score, meta in raw_results if score >= settings.min_retrieval_score]

    # 6. Load chunk metadata from DB
    chunks_for_response = []
    document_ids_accessed: list[int] = []

    if raw_results:
        chunk_ids = [r[1]["chunk_id"] for r in raw_results]
        placeholders = ",".join("?" * len(chunk_ids))

        with get_db_connection() as conn:
            rows = conn.execute(
                f"""SELECT c.id, c.chunk_text, c.document_id, c.page_number,
                           d.original_name
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE c.id IN ({placeholders})""",
                chunk_ids,
            ).fetchall()
            chunk_map = {r["id"]: dict(r) for r in rows}

        for score, meta in raw_results:
            cid = meta["chunk_id"]
            if cid not in chunk_map:
                # Stale FAISS entry — document was deleted from DB but vector
                # index was not fully cleaned up.  Skip it to avoid "Unknown"
                # sources and to prevent feeding outdated content to the LLM.
                logger.warning("Skipping stale FAISS chunk_id=%s (not found in DB)", cid)
                continue
            entry = chunk_map[cid]

            chunks_for_response.append(
                {
                    "chunk_text": entry["chunk_text"],
                    "document_id": entry["document_id"],
                    "chunk_id": cid,
                    "page_number": entry.get("page_number"),
                    "document_name": entry["original_name"],
                    "score": score,
                }
            )
            doc_id = entry["document_id"]
            if doc_id not in document_ids_accessed:
                document_ids_accessed.append(doc_id)

    # 7. Cross-encoder rerank and trim to max_retrieval_chunks
    if chunks_for_response:
        chunks_for_response = rerank(query, chunks_for_response, top_k=settings.max_retrieval_chunks)

    # 8. Generate response
    answer = generate_response(query, chunks_for_response, intent_space, conversation_history)

    latency_ms = int((time.monotonic() - t_start) * 1000)

    # 9. Get intent space display name
    with get_db_connection() as conn:
        space_row = conn.execute(
            "SELECT id, display_name FROM intent_spaces WHERE name = ?", (intent_space,)
        ).fetchone()

    intent_space_id = space_row["id"] if space_row else None
    intent_space_name = space_row["display_name"] if space_row else intent_space

    # 10. Log to DB
    with get_db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO query_logs
               (query_text, source, user_id, intent_space_id, intent_space_name,
                confidence_score, response_status, response_text, latency_ms,
                documents_accessed, cache_hit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                query, source, user_id, intent_space_id, intent_space_name,
                confidence, "success", answer, latency_ms,
                json.dumps(document_ids_accessed),
            ),
        )
        query_log_id = cur.lastrowid

        for doc_id in document_ids_accessed:
            conn.execute(
                "INSERT INTO document_access_log (document_id, query_log_id) VALUES (?, ?)",
                (doc_id, query_log_id),
            )

    result = {
        "query": query,
        "query_log_id": query_log_id,
        "intent_space": intent_space,
        "intent_space_id": intent_space_id,
        "intent_space_name": intent_space_name,
        "confidence": confidence,
        "reasoning": reasoning,
        "answer": answer,
        "sources": [
            {
                "document_name": c["document_name"],
                "document_id": c["document_id"],
                "page_number": c["page_number"],
                "score": c["score"],
            }
            for c in chunks_for_response
        ],
        "latency_ms": latency_ms,
        "status": "success",
    }

    if not conversation_history:
        _set_cache(query, result)

    return result
