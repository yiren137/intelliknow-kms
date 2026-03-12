"""Document upload, listing, deletion, re-parse, and chunk viewing."""
from __future__ import annotations
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from api.schemas import ChunkOut, DocumentOut, DocumentUploadResponse, MessageResponse
from config.settings import get_settings
from core.document_processor import process_document
from core.embedder import embed_texts
from core.vector_store import get_vector_store
from db.database import get_db_connection

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
settings = get_settings()
logger = logging.getLogger("intelliknow.documents")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _index_document(doc_id: int, file_path: str, intent_space: str, space_id: int) -> int:
    """Process, embed, and index a document. Returns chunk count."""
    chunks = process_document(file_path)
    if not chunks:
        raise ValueError("No text content extracted from document")

    texts = [c["chunk_text"] for c in chunks]
    vectors = embed_texts(texts)

    chunk_ids = []
    with get_db_connection() as conn:
        for chunk in chunks:
            cur = conn.execute(
                """INSERT INTO chunks (document_id, faiss_id, intent_space_id, chunk_text, chunk_index, page_number)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (doc_id, -1, space_id, chunk["chunk_text"], chunk["chunk_index"], chunk.get("page_number")),
            )
            chunk_ids.append(cur.lastrowid)

    store = get_vector_store(intent_space)
    faiss_ids = store.add_chunks(vectors, texts, doc_id, chunk_ids)

    with get_db_connection() as conn:
        for chunk_id, faiss_id in zip(chunk_ids, faiss_ids):
            conn.execute("UPDATE chunks SET faiss_id = ? WHERE id = ?", (faiss_id, chunk_id))
        conn.execute(
            """UPDATE documents SET status = 'indexed', chunk_count = ?, indexed_at = datetime('now')
               WHERE id = ?""",
            (len(chunks), doc_id),
        )

    return len(chunks)


# ------------------------------------------------------------------ #
# Upload                                                               #
# ------------------------------------------------------------------ #

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    intent_space: str = Form(...),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    with get_db_connection() as conn:
        space_row = conn.execute(
            "SELECT id, name FROM intent_spaces WHERE name = ? AND is_active = 1",
            (intent_space,),
        ).fetchone()
    if not space_row:
        raise HTTPException(status_code=404, detail=f"Intent space '{intent_space}' not found")

    os.makedirs(settings.uploads_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(settings.uploads_dir, unique_name)
    content = await file.read()
    file_size = len(content)
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info("Uploading '%s' (%d bytes) to intent_space=%s", file.filename, file_size, intent_space)

    with get_db_connection() as conn:
        cur = conn.execute(
            """INSERT INTO documents (filename, original_name, intent_space_id, file_type, file_size_bytes, status)
               VALUES (?, ?, ?, ?, ?, 'processing')""",
            (unique_name, file.filename, space_row["id"], ext.lstrip("."), file_size),
        )
        doc_id = cur.lastrowid

    try:
        chunk_count = _index_document(doc_id, file_path, intent_space, space_row["id"])
        return DocumentUploadResponse(
            id=doc_id,
            original_name=file.filename or unique_name,
            intent_space=intent_space,
            chunk_count=chunk_count,
            status="indexed",
        )
    except Exception as e:
        logger.exception("Failed to process document '%s' (doc_id=%s)", file.filename, doc_id)
        with get_db_connection() as conn:
            conn.execute("UPDATE documents SET status = 'error' WHERE id = ?", (doc_id,))
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


# ------------------------------------------------------------------ #
# List                                                                  #
# ------------------------------------------------------------------ #

@router.get("", response_model=list[DocumentOut])
def list_documents(
    intent_space: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = Query(default=None, description="Filter by document name (case-insensitive substring)"),
):
    with get_db_connection() as conn:
        query = """
            SELECT d.id, d.filename, d.original_name, d.intent_space_id,
                   i.name as intent_space_name, d.file_type, d.file_size_bytes,
                   d.chunk_count, d.status, d.uploaded_at, d.indexed_at
            FROM documents d
            JOIN intent_spaces i ON d.intent_space_id = i.id
            WHERE 1=1
        """
        params: list = []
        if intent_space:
            query += " AND i.name = ?"
            params.append(intent_space)
        if status:
            query += " AND d.status = ?"
            params.append(status)
        if search:
            query += " AND d.original_name LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY d.uploaded_at DESC"
        rows = conn.execute(query, params).fetchall()

    return [DocumentOut(**dict(r)) for r in rows]


# ------------------------------------------------------------------ #
# View chunks                                                          #
# ------------------------------------------------------------------ #

@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(doc_id: int):
    with get_db_connection() as conn:
        doc = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        rows = conn.execute(
            """SELECT id, chunk_index, page_number, chunk_text
               FROM chunks WHERE document_id = ? ORDER BY chunk_index""",
            (doc_id,),
        ).fetchall()
    return [ChunkOut(**dict(r)) for r in rows]


# ------------------------------------------------------------------ #
# Re-parse                                                             #
# ------------------------------------------------------------------ #

@router.post("/{doc_id}/reparse", response_model=DocumentUploadResponse)
def reparse_document(doc_id: int):
    with get_db_connection() as conn:
        row = conn.execute(
            """SELECT d.id, d.filename, d.original_name, d.file_type,
                      i.name as intent_space_name, i.id as intent_space_id
               FROM documents d JOIN intent_spaces i ON d.intent_space_id = i.id
               WHERE d.id = ?""",
            (doc_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = os.path.join(settings.uploads_dir, row["filename"])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Source file no longer exists on disk")

    logger.info("Re-parsing doc_id=%s ('%s')", doc_id, row["original_name"])

    # Remove old chunks from FAISS and DB
    store = get_vector_store(row["intent_space_name"])
    store.remove_document_chunks(doc_id)
    with get_db_connection() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        conn.execute("UPDATE documents SET status = 'processing' WHERE id = ?", (doc_id,))

    try:
        chunk_count = _index_document(doc_id, file_path, row["intent_space_name"], row["intent_space_id"])
        return DocumentUploadResponse(
            id=doc_id,
            original_name=row["original_name"],
            intent_space=row["intent_space_name"],
            chunk_count=chunk_count,
            status="indexed",
        )
    except Exception as e:
        logger.exception("Re-parse failed for doc_id=%s", doc_id)
        with get_db_connection() as conn:
            conn.execute("UPDATE documents SET status = 'error' WHERE id = ?", (doc_id,))
        raise HTTPException(status_code=500, detail=f"Re-parse failed: {str(e)}")


# ------------------------------------------------------------------ #
# Delete                                                                #
# ------------------------------------------------------------------ #

@router.delete("/{doc_id}", response_model=MessageResponse)
def delete_document(doc_id: int):
    with get_db_connection() as conn:
        row = conn.execute(
            """SELECT d.id, d.filename, i.name as intent_space_name
               FROM documents d JOIN intent_spaces i ON d.intent_space_id = i.id
               WHERE d.id = ?""",
            (doc_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    store = get_vector_store(row["intent_space_name"])
    store.remove_document_chunks(doc_id)

    file_path = os.path.join(settings.uploads_dir, row["filename"])
    if os.path.exists(file_path):
        os.remove(file_path)

    with get_db_connection() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    return MessageResponse(message=f"Document {doc_id} deleted successfully")
