"""Tests for document upload, listing, and deletion."""
import os
import time
import pytest


def _wait_for_indexed(client, doc_id: int, timeout: int = 30) -> dict:
    """Poll until a document reaches 'indexed' status, then return it."""
    for _ in range(timeout):
        docs = client.get("/api/v1/documents").json()
        matching = [d for d in docs if d["id"] == doc_id]
        if matching and matching[0]["status"] == "indexed":
            return matching[0]
        time.sleep(1)
    pytest.fail(f"Document {doc_id} did not reach 'indexed' status within {timeout}s")


def test_list_documents(client):
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_documents_schema(client):
    resp = client.get("/api/v1/documents")
    docs = resp.json()
    if docs:
        doc = docs[0]
        for field in ["id", "filename", "original_name", "intent_space_id", "file_type", "chunk_count", "status"]:
            assert field in doc


def test_list_documents_filter_by_intent_space(client):
    resp = client.get("/api/v1/documents?intent_space=hr")
    assert resp.status_code == 200
    docs = resp.json()
    for doc in docs:
        assert doc["intent_space_name"] == "hr"


def test_upload_unsupported_file_type_returns_400(client):
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
        data={"intent_space": "hr"},
    )
    assert resp.status_code == 400


def test_upload_to_nonexistent_intent_space_returns_404(client):
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.docx", b"fake docx content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"intent_space": "nonexistent_space"},
    )
    assert resp.status_code == 404


def test_upload_hr_document(client, hr_doc_path):
    if not os.path.exists(hr_doc_path):
        pytest.skip("HR test document not found — run population script first")

    with open(hr_doc_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_hr_handbook.pdf", f, "application/pdf")},
            data={"intent_space": "hr"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # Upload returns immediately; status may be 'processing' or already 'indexed'
    assert body["status"] in ("indexed", "processing")
    assert body["intent_space"] == "hr"

    doc = _wait_for_indexed(client, body["id"])
    assert doc["chunk_count"] > 0


def test_upload_legal_document(client, legal_doc_path):
    if not os.path.exists(legal_doc_path):
        pytest.skip("Legal test document not found")

    with open(legal_doc_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_legal_compliance.pdf", f, "application/pdf")},
            data={"intent_space": "legal"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("indexed", "processing")
    _wait_for_indexed(client, body["id"])


def test_upload_finance_document(client, finance_doc_path):
    if not os.path.exists(finance_doc_path):
        pytest.skip("Finance test document not found")

    with open(finance_doc_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_finance_policies.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"intent_space": "finance"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("indexed", "processing")
    _wait_for_indexed(client, body["id"])


def test_upload_general_document(client, general_doc_path):
    if not os.path.exists(general_doc_path):
        pytest.skip("General test document not found")

    with open(general_doc_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_general_handbook.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"intent_space": "general"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("indexed", "processing")
    _wait_for_indexed(client, body["id"])


def test_delete_nonexistent_document_returns_404(client):
    resp = client.delete("/api/v1/documents/999999")
    assert resp.status_code == 404


def test_upload_and_delete_document(client, hr_doc_path):
    if not os.path.exists(hr_doc_path):
        pytest.skip("HR test document not found")

    with open(hr_doc_path, "rb") as f:
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("temp_upload.pdf", f, "application/pdf")},
            data={"intent_space": "hr"},
        )
    assert upload.status_code == 200
    doc_id = upload.json()["id"]

    # Wait for indexing before deleting
    _wait_for_indexed(client, doc_id)

    delete = client.delete(f"/api/v1/documents/{doc_id}")
    assert delete.status_code == 200

    # Confirm deleted
    docs = client.get("/api/v1/documents").json()
    ids = [d["id"] for d in docs]
    assert doc_id not in ids
