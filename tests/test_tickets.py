import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation_dispatcher import automation_dispatcher
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.core.tickets import ticket_store
from app.main import app
from app.models import Automation


@pytest.fixture(autouse=True)
def configure_database(tmp_path, monkeypatch):
    db_path = tmp_path / "tickets.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    asyncio.run(dispose_engine())
    yield
    asyncio.run(dispose_engine())
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_ticket_overrides():
    asyncio.run(ticket_store.reset())
    yield
    asyncio.run(ticket_store.reset())


@pytest.fixture(autouse=True)
def reset_automation_events():
    asyncio.run(automation_dispatcher.reset())
    yield
    asyncio.run(automation_dispatcher.reset())


def test_ticket_create_dispatches_automation_event():
    with TestClient(app) as client:
        payload = {
            "subject": "Inventory sync outage",
            "customer": "Quest Logistics",
            "customer_email": "ops@quest-logistics.example",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Warehouse scanners are unable to sync inventory updates to ERP.",
        }

        response = client.post("/tickets", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["ticket_id"].startswith("TD-")
        assert data["detail"] == "Ticket created successfully."
        assert data["redirect_url"]

        detail_response = client.get(data["redirect_url"])
        assert detail_response.status_code == 200
        html = detail_response.text
        assert payload["subject"] in html
        assert "Ticket created successfully." in html

        events = asyncio.run(automation_dispatcher.list_events())
        assert any(
            event.event_type == "Ticket Created" and event.ticket_id == data["ticket_id"]
            for event in events
        )


def test_ticket_create_triggers_event_automations():
    async def _seed_automation() -> int:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            automation = Automation(
                name="Notify on creation",
                description="Dispatch actions when tickets are created.",
                playbook="Support operations",
                kind="event",
                trigger="Ticket Created",
                status="Active",
                ticket_actions=[
                    {"action": "send-ntfy-notification", "value": "Ticket {{ ticket.id }} created."}
                ],
            )
            session.add(automation)
            await session.commit()
            return automation.id

    automation_id = asyncio.run(_seed_automation())

    with TestClient(app) as client:
        payload = {
            "subject": "Network edge outage",
            "customer": "Quest Logistics",
            "customer_email": "noc@quest-logistics.example",
            "status": "Open",
            "priority": "Critical",
            "team": "Tier 2",
            "assignment": "On-call engineer",
            "queue": "Incident response",
            "category": "Incident",
            "summary": "Core edge routers unreachable from multiple sites.",
        }

        response = client.post("/tickets", json=payload)
        assert response.status_code == 201

    events = asyncio.run(automation_dispatcher.list_events())
    triggered = [
        event
        for event in events
        if event.event_type == "Automation Triggered"
        and event.payload.get("automation_id") == automation_id
    ]
    assert triggered

    async def _fetch_last_trigger() -> datetime | None:
        engine = await get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            record = await session.get(Automation, automation_id)
            return record.last_trigger_at if record else None

    last_trigger = asyncio.run(_fetch_last_trigger())
    assert last_trigger is not None


def test_ticket_new_route_renders_creation_page():
    with TestClient(app) as client:
        response = client.get("/tickets/new")
        assert response.status_code == 200
        html = response.text
        assert "Create new ticket" in html
        assert "Ticket details" in html
        assert "name=\"subject\"" in html


def test_tickets_route_redirects_to_create_when_query_flag_present():
    with TestClient(app) as client:
        response = client.get("/tickets?new=1", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/tickets/new")


def test_api_ticket_creation_endpoint():
    with TestClient(app) as client:
        payload = {
            "subject": "VPN tunnel degraded",
            "customer": "Blue Harbor Finance",
            "customer_email": "infra@blueharbor.example",
            "status": "Open",
            "priority": "High",
            "team": "Network operations",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Incident",
            "summary": "Automated monitoring detected packet loss exceeding threshold.",
        }

        response = client.post("/api/tickets", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["ticket"]["subject"] == payload["subject"]
        assert data["ticket_id"].startswith("TD-")

        redirect = data["redirect_url"]
        assert redirect
        detail_response = client.get(redirect)
        assert detail_response.status_code == 200
        assert payload["subject"] in detail_response.text


def test_api_ticket_creation_validation_errors():
    with TestClient(app) as client:
        payload = {
            "subject": "",
            "customer": "Example Corp",
            "customer_email": "not-an-email",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "General",
            "category": "Support",
            "summary": "Placeholder summary",
        }

        response = client.post("/api/tickets", json=payload)
        assert response.status_code == 422
        body = response.json()
        assert "subject" in str(body)
        assert "customer_email" in str(body)


def test_ticket_create_form_validation_errors_rendered():
    with TestClient(app) as client:
        form_payload = {
            "subject": " ",
            "customer": "Quest Logistics",
            "customer_email": "invalid-email",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Investigating packet loss impacting the VPN tunnel between HQ and warehouse sites.",
        }

        response = client.post("/tickets", data=form_payload)
        assert response.status_code == 422
        html = response.text
        assert "Subject cannot be empty." in html
        assert "Customer email must be a valid email address." in html
        assert "value=\"invalid-email\"" in html


def test_ticket_update_persists_overrides():
    with TestClient(app) as client:
        form_payload = {
            "subject": "Network throughput review",
            "customer": "Quest Logistics",
            "customer_email": "quest.labs@example.com",
            "status": "Pending",
            "priority": "Medium",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Coordinating bandwidth test plan with the carrier support team.",
        }
        response = client.post(
            "/tickets/TD-4821",
            data=form_payload,
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.endswith("?saved=1")

        detail_response = client.get(location)
        assert detail_response.status_code == 200
        html = detail_response.text
        assert "Ticket changes saved successfully." in html
        assert "Network throughput review" in html
        assert "Coordinating bandwidth test plan with the carrier support team." in html
        assert "value=\"Pending\" selected" in html


def test_ticket_update_validation_errors_reported():
    with TestClient(app) as client:
        form_payload = {
            "subject": " ",
            "customer": "Quest Logistics",
            "customer_email": "invalid-email",
            "status": "Open",
            "priority": "High",
            "team": "Tier 1",
            "assignment": "Unassigned",
            "queue": "Critical response",
            "category": "Support",
            "summary": "Investigating packet loss impacting the VPN tunnel between HQ and warehouse sites.",
        }
        response = client.post("/tickets/TD-4821", data=form_payload)
        assert response.status_code == 422
        html = response.text
        assert "Subject cannot be empty." in html
        assert "Customer email must be a valid email address." in html
        # ensure the submitted (invalid) values are preserved for user correction
        assert "value=\"\"" in html
        assert "value=\"invalid-email\"" in html


def test_ticket_reply_successful_submission_appends_history():
    with TestClient(app) as client:
        reply_payload = {
            "to": "quest.labs@example.com",
            "cc": "network.ops@example.com",
            "template": "custom",
            "message": "We are continuing to investigate and will follow up shortly.\nThank you for your patience.",
            "public_reply": "on",
            "add_signature": "on",
        }
        response = client.post(
            "/tickets/TD-4821/reply",
            data=reply_payload,
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.endswith("?reply=1")

        detail_response = client.get(location)
        assert detail_response.status_code == 200
        html = detail_response.text
        assert "Reply sent successfully." in html
        assert "We are continuing to investigate" in html
        assert "Thank you for your patience." in html
        assert "Super Admin" in html


def test_ticket_reply_validation_errors_reported():
    with TestClient(app) as client:
        reply_payload = {
            "to": "not-an-email",
            "cc": "",
            "template": "custom",
            "message": " ",
        }
        response = client.post(
            "/tickets/TD-4821/reply",
            data=reply_payload,
        )
        assert response.status_code == 422
        html = response.text
        assert "Recipient must be a valid email address." in html
        assert "Message cannot be empty." in html
        assert "Query for Opensource Project" in html
