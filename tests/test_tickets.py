import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.tickets import ticket_store
from app.main import app


@pytest.fixture(autouse=True)
def reset_ticket_overrides():
    asyncio.run(ticket_store.reset())
    yield
    asyncio.run(ticket_store.reset())


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
