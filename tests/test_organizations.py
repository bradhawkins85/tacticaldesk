import asyncio
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.tickets import ticket_store
from app.main import app
from app.main import build_ticket_records


@pytest.fixture(autouse=True)
def reset_ticket_store():
    asyncio.run(ticket_store.reset())
    yield
    asyncio.run(ticket_store.reset())


@pytest.fixture(autouse=True)
def organization_db(tmp_path, monkeypatch):
    db_path = tmp_path / "organizations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_seeded_organizations_present_in_api_and_ui():
    with TestClient(app) as client:
        response = client.get("/api/organizations")
        assert response.status_code == 200
        payload = response.json()
        names = {item["name"] for item in payload}
        assert "Quest Logistics" in names
        assert "Northwind Retail" in names

        html_response = client.get("/admin/organisations")
        assert html_response.status_code == 200
        html = html_response.text
        assert "Organisation registry" in html
        assert "Quest Logistics" in html
        assert "Northwind Retail" in html


def test_create_update_and_archive_organization():
    with TestClient(app) as client:
        create_payload = {
            "name": "Acme Global",
            "slug": "acme-global",
            "contact_email": "ops@acme.example",
            "description": "Tiered managed services customer.",
        }
        create_response = client.post("/api/organizations", json=create_payload)
        assert create_response.status_code == 201
        created = create_response.json()
        organization_id = created["id"]
        assert created["slug"] == "acme-global"

        update_payload = {
            "name": "Acme Global Holdings",
            "description": "Updated descriptor for Acme.",
        }
        update_response = client.patch(
            f"/api/organizations/{organization_id}", json=update_payload
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Acme Global Holdings"
        assert updated["description"] == "Updated descriptor for Acme."

        archive_response = client.patch(
            f"/api/organizations/{organization_id}", json={"is_archived": True}
        )
        assert archive_response.status_code == 200
        archived = archive_response.json()
        assert archived["is_archived"] is True

        html_response = client.get("/admin/organisations")
        assert html_response.status_code == 200
        html = html_response.text
        assert "Acme Global Holdings" in html
        assert "data-status=\"archived\"" in html
        assert "Restore" in html


def test_duplicate_slug_conflict():
    with TestClient(app) as client:
        payload = {
            "name": "Contoso Services",
            "slug": "contoso-services",
        }
        first = client.post("/api/organizations", json=payload)
        assert first.status_code == 201

        second = client.post("/api/organizations", json=payload)
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]


def test_migration_recovers_missing_organization_columns(tmp_path):
    db_path = tmp_path / "organizations.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT,
                contact_email TEXT,
                is_archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO organizations (name, slug, description, contact_email, is_archived)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Legacy Org",
                "legacy-org",
                "Organization created before timestamp columns existed.",
                "legacy@example.com",
                0,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as client:
        response = client.get("/admin/organisations")
        assert response.status_code == 200

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute("PRAGMA table_info('organizations')")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        connection.close()

    assert "created_at" in columns
    assert "updated_at" in columns


def test_delete_organization_cascades_contacts_and_tickets():
    with TestClient(app) as client:
        create_payload = {
            "name": "Arc Light Solutions",
            "slug": "arc-light-solutions",
            "contact_email": "support@arclight.example",
            "description": "Premium managed services tenant.",
        }
        create_response = client.post("/api/organizations", json=create_payload)
        assert create_response.status_code == 201
        organization_id = create_response.json()["id"]

        contact_payload = {
            "name": "Elena Rivera",
            "job_title": "Operations Director",
            "email": "escalations@arclight.example",
        }
        contact_response = client.post(
            f"/api/organizations/{organization_id}/contacts",
            json=contact_payload,
        )
        assert contact_response.status_code == 201

        ticket_payload = {
            "subject": "License provisioning failure",
            "customer": "Arc Light Solutions",
            "customer_email": "escalations@arclight.example",
            "status": "Open",
            "priority": "High",
            "team": "Tier 2",
            "assignment": "Escalations",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Agents report license activation timeout when onboarding new hires.",
        }
        ticket_response = client.post("/tickets", json=ticket_payload)
        assert ticket_response.status_code == 201
        created_ticket = ticket_response.json()
        ticket_id = created_ticket["ticket_id"]

        now_before = datetime.now(timezone.utc)
        tickets_before = asyncio.run(
            ticket_store.apply_overrides(build_ticket_records(now_before))
        )
        assert any(ticket["id"] == ticket_id for ticket in tickets_before)

        delete_response = client.delete(f"/api/organizations/{organization_id}")
        assert delete_response.status_code == 204

        get_response = client.get(f"/api/organizations/{organization_id}")
        assert get_response.status_code == 404

        contacts_response = client.get(
            f"/api/organizations/{organization_id}/contacts"
        )
        assert contacts_response.status_code == 404

        now_after = datetime.now(timezone.utc)
        tickets_after = asyncio.run(
            ticket_store.apply_overrides(build_ticket_records(now_after))
        )
        assert all(
            ticket.get("customer") != "Arc Light Solutions" for ticket in tickets_after
        )
        assert all(
            ticket.get("customer_email") != "escalations@arclight.example"
            for ticket in tickets_after
        )

        ticket_detail = client.get(f"/tickets/{ticket_id}")
        assert ticket_detail.status_code == 404
