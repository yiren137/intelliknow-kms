"""Feedback endpoint for thumbs up/down on query responses."""
from fastapi import APIRouter, HTTPException
from api.schemas import FeedbackRequest, MessageResponse
from db.database import get_db_connection

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("/{query_log_id}", response_model=MessageResponse)
def submit_feedback(query_log_id: int, body: FeedbackRequest):
    if body.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback must be 1 (thumbs up) or -1 (thumbs down)")

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id FROM query_logs WHERE id = ?", (query_log_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Query log entry not found")

        conn.execute(
            "UPDATE query_logs SET feedback = ? WHERE id = ?",
            (body.feedback, query_log_id),
        )

    return MessageResponse(message="Feedback recorded", detail={"query_log_id": query_log_id, "feedback": body.feedback})
