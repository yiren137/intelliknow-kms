"""Tests for intent space CRUD endpoints."""
import pytest


def test_list_intent_spaces_returns_defaults(client):
    resp = client.get("/api/v1/intent-spaces")
    assert resp.status_code == 200
    spaces = resp.json()
    assert len(spaces) >= 4
    names = {s["name"] for s in spaces}
    assert {"hr", "legal", "finance", "general"}.issubset(names)


def test_list_intent_spaces_schema(client):
    resp = client.get("/api/v1/intent-spaces")
    space = resp.json()[0]
    for field in ["id", "name", "display_name", "description", "keywords", "confidence_threshold", "is_active", "created_at", "document_count"]:
        assert field in space, f"Missing field: {field}"


def test_create_intent_space(client):
    # Clean up if left over from a previous run
    spaces = client.get("/api/v1/intent-spaces").json()
    existing = next((s for s in spaces if s["name"] == "test_space"), None)
    if existing:
        client.delete(f"/api/v1/intent-spaces/{existing['id']}")

    resp = client.post("/api/v1/intent-spaces", json={
        "name": "test_space",
        "display_name": "Test Space",
        "description": "Temporary space for testing",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "test_space"
    assert body["is_active"] is True


def test_create_duplicate_intent_space_returns_409(client):
    resp = client.post("/api/v1/intent-spaces", json={
        "name": "hr",
        "display_name": "HR Duplicate",
        "description": "should fail",
    })
    assert resp.status_code == 409


def test_create_intent_space_invalid_name_returns_422(client):
    resp = client.post("/api/v1/intent-spaces", json={
        "name": "Has Spaces!",
        "display_name": "Invalid",
        "description": "",
    })
    assert resp.status_code == 422


def test_update_intent_space(client):
    # Get the id of 'general' space
    spaces = client.get("/api/v1/intent-spaces").json()
    general = next(s for s in spaces if s["name"] == "general")
    space_id = general["id"]

    resp = client.put(f"/api/v1/intent-spaces/{space_id}", json={
        "description": "Updated general description"
    })
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated general description"

    # Restore original
    client.put(f"/api/v1/intent-spaces/{space_id}", json={
        "description": "General company knowledge, announcements, miscellaneous docs"
    })


def test_delete_general_space_returns_400(client):
    spaces = client.get("/api/v1/intent-spaces").json()
    general = next(s for s in spaces if s["name"] == "general")
    resp = client.delete(f"/api/v1/intent-spaces/{general['id']}")
    assert resp.status_code == 400


def test_delete_nonexistent_space_returns_404(client):
    resp = client.delete("/api/v1/intent-spaces/999999")
    assert resp.status_code == 404


def test_create_and_delete_custom_space(client):
    create = client.post("/api/v1/intent-spaces", json={
        "name": "temp_delete_test",
        "display_name": "Temp",
        "description": "Will be deleted",
    })
    assert create.status_code == 201
    space_id = create.json()["id"]

    delete = client.delete(f"/api/v1/intent-spaces/{space_id}")
    assert delete.status_code == 200
