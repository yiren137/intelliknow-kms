"""Full query pipeline: classify → embed → search → respond → log."""
from __future__ import annotations
import json
import time
from typing import Optional

from config.settings import get_settings
from db.database import get_db_connection
from core.embedder import embed_query
from core.vector_store import get_vector_store
from core.classifier import classify_query
from core.responder import generate_response

settings = get_settings()


def _get_confidence_threshold(intent_space: str) -> float:
    """Return the configured confidence threshold for an intent space."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT confidence_threshold FROM intent_spaces WHERE name = ?",
            (intent_space,),
        ).fetchone()
    if row and row["confidence_threshold"] is not None:
        return float(row["confidence_threshold"])
    return 0.7


def run_query(
    query: str,
    source: str = "api",
    user_id: Optional[str] = None,
) -> dict:
    """Execute the full query pipeline and return a result dict."""
    t_start = time.monotonic()

    # 1. Classify intent
    classification = classify_query(query)
    intent_space = classification["intent_space"]
    confidence = classification.get("confidence", 0.5)
    reasoning = classification.get("reasoning", "")

    # 2. Apply confidence threshold — fall back to 'general' if below threshold
    threshold = _get_confidence_threshold(intent_space)
    if confidence < threshold and intent_space != "general":
        reasoning = (
            f"Confidence {confidence:.2f} below threshold {threshold:.2f} for '{intent_space}'; "
            f"falling back to 'general'. Original: {reasoning}"
        )
        intent_space = "general"

    # 3. Embed query
    q_vec = embed_query(query)

    # 4. Vector search
    store = get_vector_store(intent_space)
    raw_results = store.search(q_vec, top_k=settings.max_retrieval_chunks)

    # 5. Load chunk metadata from DB
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
            if cid in chunk_map:
                entry = chunk_map[cid]
            else:
                entry = {
                    "chunk_text": meta["chunk_text"],
                    "document_id": meta["document_id"],
                    "chunk_id": cid,
                    "page_number": None,
                    "original_name": "Unknown",
                }

            chunks_for_response.append(
                {
                    "chunk_text": entry.get("chunk_text", meta["chunk_text"]),
                    "document_id": entry.get("document_id", meta["document_id"]),
                    "chunk_id": cid,
                    "page_number": entry.get("page_number"),
                    "document_name": entry.get("original_name", "Unknown"),
                    "score": score,
                }
            )
            doc_id = entry.get("document_id", meta["document_id"])
            if doc_id not in document_ids_accessed:
                document_ids_accessed.append(doc_id)

    # 6. Generate response
    answer = generate_response(query, chunks_for_response, intent_space)

    latency_ms = int((time.monotonic() - t_start) * 1000)

    # 7. Get intent space display name
    with get_db_connection() as conn:
        space_row = conn.execute(
            "SELECT id, display_name FROM intent_spaces WHERE name = ?", (intent_space,)
        ).fetchone()

    intent_space_id = space_row["id"] if space_row else None
    intent_space_name = space_row["display_name"] if space_row else intent_space

    # 8. Log to DB
    with get_db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO query_logs
               (query_text, source, user_id, intent_space_id, intent_space_name,
                confidence_score, response_status, response_text, latency_ms, documents_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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

    return {
        "query": query,
        "intent_space": intent_space,
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
