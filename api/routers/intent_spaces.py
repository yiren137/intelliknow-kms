"""CRUD for intent spaces."""
from fastapi import APIRouter, HTTPException
from api.schemas import IntentSpaceCreate, IntentSpaceOut, IntentSpaceUpdate, MessageResponse
from db.database import get_db_connection

router = APIRouter(prefix="/api/v1/intent-spaces", tags=["intent-spaces"])


def _row_to_out(row: dict) -> IntentSpaceOut:
    return IntentSpaceOut(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        description=row["description"] or "",
        keywords=row["keywords"] or "",
        confidence_threshold=row["confidence_threshold"] if row["confidence_threshold"] is not None else 0.7,
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        document_count=row.get("document_count", 0) or 0,
        accuracy_rate=row.get("accuracy_rate"),
    )


@router.get("", response_model=list[IntentSpaceOut])
def list_intent_spaces():
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT i.id, i.name, i.display_name, i.description, i.keywords,
                      i.confidence_threshold, i.is_active, i.created_at,
                      COUNT(DISTINCT d.id) as document_count,
                      AVG(CASE WHEN ql.response_status = 'success' THEN ql.confidence_score END) as accuracy_rate
               FROM intent_spaces i
               LEFT JOIN documents d ON i.id = d.intent_space_id AND d.status = 'indexed'
               LEFT JOIN query_logs ql ON i.id = ql.intent_space_id
               GROUP BY i.id
               ORDER BY i.created_at"""
        ).fetchall()
    return [_row_to_out(dict(r)) for r in rows]


@router.post("", response_model=IntentSpaceOut, status_code=201)
def create_intent_space(body: IntentSpaceCreate):
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM intent_spaces WHERE name = ?", (body.name,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Intent space '{body.name}' already exists")

        cur = conn.execute(
            """INSERT INTO intent_spaces (name, display_name, description, keywords, confidence_threshold)
               VALUES (?, ?, ?, ?, ?)""",
            (body.name, body.display_name, body.description, body.keywords, body.confidence_threshold),
        )
        row = conn.execute(
            """SELECT *, 0 as document_count, NULL as accuracy_rate
               FROM intent_spaces WHERE id = ?""",
            (cur.lastrowid,),
        ).fetchone()

    return _row_to_out(dict(row))


@router.put("/{space_id}", response_model=IntentSpaceOut)
def update_intent_space(space_id: int, body: IntentSpaceUpdate):
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM intent_spaces WHERE id = ?", (space_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Intent space not found")

        updates = {}
        if body.display_name is not None:
            updates["display_name"] = body.display_name
        if body.description is not None:
            updates["description"] = body.description
        if body.keywords is not None:
            updates["keywords"] = body.keywords
        if body.confidence_threshold is not None:
            updates["confidence_threshold"] = body.confidence_threshold
        if body.is_active is not None:
            updates["is_active"] = int(body.is_active)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [space_id]
            conn.execute(f"UPDATE intent_spaces SET {set_clause} WHERE id = ?", values)

        row = conn.execute(
            """SELECT i.*, COUNT(DISTINCT d.id) as document_count,
                      AVG(CASE WHEN ql.response_status = 'success' THEN ql.confidence_score END) as accuracy_rate
               FROM intent_spaces i
               LEFT JOIN documents d ON i.id = d.intent_space_id AND d.status = 'indexed'
               LEFT JOIN query_logs ql ON i.id = ql.intent_space_id
               WHERE i.id = ?
               GROUP BY i.id""",
            (space_id,),
        ).fetchone()

    return _row_to_out(dict(row))


@router.delete("/{space_id}", response_model=MessageResponse)
def delete_intent_space(space_id: int):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT name FROM intent_spaces WHERE id = ?", (space_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intent space not found")

        if row["name"] == "general":
            raise HTTPException(status_code=400, detail="Cannot delete the default 'general' intent space")

        conn.execute("DELETE FROM intent_spaces WHERE id = ?", (space_id,))

    return MessageResponse(message=f"Intent space {space_id} deleted")
