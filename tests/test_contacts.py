import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def contact_db(tmp_path, monkeypatch):
    db_path = tmp_path / "contacts.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_seed_contacts_present_in_api_and_ui():
    with TestClient(app) as client:
        org_response = client.get("/api/organizations")
        assert org_response.status_code == 200
        organizations = org_response.json()
        quest = next((org for org in organizations if org["slug"] == "quest-logistics"), None)
        assert quest is not None

        contacts_response = client.get(f"/api/organizations/{quest['id']}/contacts")
        assert contacts_response.status_code == 200
        contacts = contacts_response.json()
        contact_names = {contact["name"] for contact in contacts}
        assert "Alicia Patel" in contact_names

        html_response = client.get(f"/admin/organisations/{quest['id']}/contacts")
        assert html_response.status_code == 200
        html = html_response.text
        assert "Alicia Patel" in html
        assert "IT Service Manager" in html


def test_contact_crud_flow():
    with TestClient(app) as client:
        org_payload = {
            "name": "Blue Ocean Analytics",
            "slug": "blue-ocean-analytics",
            "contact_email": "hello@blueocean.example",
        }
        create_org = client.post("/api/organizations", json=org_payload)
        assert create_org.status_code == 201
        organization_id = create_org.json()["id"]

        create_contact_payload = {
            "name": "Jordan Smith",
            "job_title": "CTO",
            "email": "jordan.smith@blueocean.example",
            "phone": "+1-503-555-0198",
            "notes": "Primary escalation contact for platform incidents.",
        }
        create_contact = client.post(
            f"/api/organizations/{organization_id}/contacts",
            json=create_contact_payload,
        )
        assert create_contact.status_code == 201
        created_contact = create_contact.json()
        contact_id = created_contact["id"]
        assert created_contact["name"] == "Jordan Smith"
        assert created_contact["job_title"] == "CTO"

        update_payload = {
            "job_title": "Chief Technology Officer",
            "phone": "+1-503-555-0120",
            "notes": None,
        }
        update_response = client.patch(
            f"/api/organizations/{organization_id}/contacts/{contact_id}",
            json=update_payload,
        )
        assert update_response.status_code == 200
        updated_contact = update_response.json()
        assert updated_contact["job_title"] == "Chief Technology Officer"
        assert updated_contact["phone"] == "+1-503-555-0120"
        assert updated_contact["notes"] is None

        delete_response = client.delete(
            f"/api/organizations/{organization_id}/contacts/{contact_id}"
        )
        assert delete_response.status_code == 204

        list_response = client.get(f"/api/organizations/{organization_id}/contacts")
        assert list_response.status_code == 200
        assert list_response.json() == []

        # verify HTML view renders without the deleted contact
        html_response = client.get(
            f"/admin/organisations/{organization_id}/contacts"
        )
        assert html_response.status_code == 200
        assert "Jordan Smith" not in html_response.text
