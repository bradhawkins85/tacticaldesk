from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def _configure_database(tmp_path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _create_space(client: TestClient, name: str, slug: str | None = None) -> dict:
    payload = {"name": name}
    if slug is not None:
        payload["slug"] = slug
    response = client.post("/api/knowledge/spaces", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_document(client: TestClient, space_id: int, **data: object) -> dict:
    payload = {"title": "Runbook", "content": "Initial body."}
    payload.update(data)
    response = client.post(f"/api/knowledge/spaces/{space_id}/documents", json=payload)
    assert response.status_code == 201
    return response.json()


def test_knowledge_space_document_lifecycle():
    with TestClient(app) as client:
        space = _create_space(client, "Operations", slug="operations")
        space_id = space["id"]

        list_response = client.get("/api/knowledge/spaces")
        assert list_response.status_code == 200
        spaces = list_response.json()
        assert any(item["slug"] == "operations" for item in spaces)

        document = _create_document(
            client,
            space_id,
            title="VPN troubleshooting playbook",
            content="Verify tunnel status and restart the concentrator if needed.",
            summary="Emergency steps for VPN outages.",
            is_published=True,
        )
        assert document["version"] == 1
        assert document["is_published"] is True

        update_response = client.patch(
            f"/api/knowledge/documents/{document['id']}",
            json={"content": "Updated remediation steps.", "summary": "Updated summary."},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["version"] == 2
        assert updated["summary"] == "Updated summary."

        versions_response = client.get(
            f"/api/knowledge/documents/{document['id']}/versions"
        )
        assert versions_response.status_code == 200
        versions = versions_response.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

        html_response = client.get(
            "/knowledge", params={"space": "operations", "document": document["slug"]}
        )
        assert html_response.status_code == 200
        html = html_response.text
        assert "VPN troubleshooting playbook" in html
        assert "Updated remediation steps." in html
        assert "Revision history" in html


def test_document_parent_must_match_space():
    with TestClient(app) as client:
        primary_space = _create_space(client, "Primary")
        secondary_space = _create_space(client, "Secondary")

        parent_doc = _create_document(
            client,
            primary_space["id"],
            title="Parent", content="Parent body", slug="parent"
        )

        invalid_response = client.post(
            f"/api/knowledge/spaces/{secondary_space['id']}/documents",
            json={
                "title": "Child",
                "content": "Child body",
                "parent_id": parent_doc["id"],
            },
        )
        assert invalid_response.status_code == 400
        assert "Parent document must belong to the same space" in invalid_response.json()["detail"]

        valid_child = _create_document(
            client,
            primary_space["id"],
            title="Child",
            content="Child body",
            parent_id=parent_doc["id"],
        )
        assert valid_child["parent_id"] == parent_doc["id"]

        update_response = client.patch(
            f"/api/knowledge/documents/{valid_child['id']}",
            json={"parent_id": None},
        )
        assert update_response.status_code == 200
        assert update_response.json()["parent_id"] is None
