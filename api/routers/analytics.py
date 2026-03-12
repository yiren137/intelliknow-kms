"""Analytics endpoints."""
from fastapi import APIRouter, Query
from api.schemas import (
    AnalyticsSummary, QueryLogEntry, DocumentAccessStat, DailyVolume
)
from db.database import get_db_connection

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary():
    with get_db_connection() as conn:
        ql = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN response_status='success' THEN 1 ELSE 0 END) as success,
                      AVG(latency_ms) as avg_latency
               FROM query_logs"""
        ).fetchone()

        doc_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status='indexed'"
        ).fetchone()[0]

        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        top_spaces = conn.execute(
            """SELECT intent_space_name as name, COUNT(*) as count
               FROM query_logs
               WHERE intent_space_name IS NOT NULL
               GROUP BY intent_space_name
               ORDER BY count DESC
               LIMIT 5"""
        ).fetchall()

    total = ql["total"] or 0
    success = ql["success"] or 0
    return AnalyticsSummary(
        total_queries=total,
        successful_queries=success,
        success_rate=round(success / total, 4) if total else 0.0,
        total_documents=doc_count,
        total_chunks=chunk_count,
        avg_latency_ms=round(ql["avg_latency"] or 0, 1),
        top_intent_spaces=[dict(r) for r in top_spaces],
    )


@router.get("/queries", response_model=list[QueryLogEntry])
def analytics_queries(
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    source: str | None = None,
):
    with get_db_connection() as conn:
        sql = """SELECT id, query_text, source, user_id, intent_space_name,
                        confidence_score, response_status, latency_ms, created_at
                 FROM query_logs WHERE 1=1"""
        params: list = []
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()

    return [QueryLogEntry(**dict(r)) for r in rows]


@router.get("/documents", response_model=list[DocumentAccessStat])
def analytics_documents():
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT d.id as document_id, d.original_name,
                      COUNT(dal.id) as access_count,
                      i.display_name as intent_space_name
               FROM documents d
               JOIN intent_spaces i ON d.intent_space_id = i.id
               LEFT JOIN document_access_log dal ON d.id = dal.document_id
               GROUP BY d.id
               ORDER BY access_count DESC"""
        ).fetchall()

    return [DocumentAccessStat(**dict(r)) for r in rows]


@router.get("/daily", response_model=list[DailyVolume])
def analytics_daily(days: int = Query(default=30, le=365)):
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT date(created_at) as date, COUNT(*) as query_count
               FROM query_logs
               WHERE created_at >= date('now', ? || ' days')
               GROUP BY date(created_at)
               ORDER BY date""",
            (f"-{days}",),
        ).fetchall()

    return [DailyVolume(**dict(r)) for r in rows]
