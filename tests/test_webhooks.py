from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.main import app
from app.models import Automation, WebhookDelivery, utcnow


@pytest.fixture(autouse=True)
def webhook_db(tmp_path, monkeypatch):
    db_path = tmp_path / "webhooks.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    asyncio.run(dispose_engine())
    get_settings.cache_clear()


async def _create_delivery(event_id: str = "whk-test") -> None:
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        now = utcnow()
        delivery = WebhookDelivery(
            event_id=event_id,
            endpoint="https://hooks.example/webhook",
            status="retrying",
            last_attempt_at=now - timedelta(minutes=2),
            next_retry_at=now + timedelta(minutes=3),
        )
        session.add(delivery)
        await session.commit()


async def _create_https_post_automation() -> None:
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        automation = Automation(
            name="Webhook responder",
            description="Notify on HTTPS POST webhook",
            playbook="Alerting",
            kind="event",
            trigger="HTTP POST Webhook Received",
            ticket_actions=[
                {
                    "action": "send-ntfy-notification",
                    "value": "Webhook summary: {{ webhook.summary }}",
                }
            ],
        )
        session.add(automation)
        await session.commit()


def test_pause_resume_delete_webhook():
    with TestClient(app) as client:
        asyncio.run(_create_delivery("whk-900"))

        pause_response = client.post("/api/webhooks/whk-900/pause")
        assert pause_response.status_code == 200
        paused_payload = pause_response.json()
        assert paused_payload["status"] == "paused"
        assert paused_payload["next_retry_at"] is None

        resume_response = client.post("/api/webhooks/whk-900/resume")
        assert resume_response.status_code == 200
        resumed_payload = resume_response.json()
        assert resumed_payload["status"] == "retrying"
        assert resumed_payload["next_retry_at"] is not None

        delete_response = client.delete("/api/webhooks/whk-900")
        assert delete_response.status_code == 204

        list_response = client.get("/api/webhooks")
        assert list_response.status_code == 200
        remaining_ids = {item["event_id"] for item in list_response.json()}
        assert "whk-900" not in remaining_ids


def test_https_post_webhook_receiver_maps_standard_fields():
    payload = {
        "id": "evt-100",
        "type": "alert.raised",
        "summary": "Incident acknowledged",
        "details": "An operator acknowledged the incident.",
        "severity": "high",
        "source": "operations-monitor",
        "timestamp": "2025-01-01T10:00:00+00:00",
        "url": "https://status.example/incidents/evt-100",
        "tags": ["incident", "acknowledged"],
    }

    with TestClient(app) as client:
        response = client.post("/api/webhooks/https-post", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "webhook.summary" in body["mapped_keys"]
    variables = body["variables"]
    assert variables["webhook.summary"] == "Incident acknowledged"
    assert variables["webhook.details"] == "An operator acknowledged the incident."
    assert variables["webhook.severity"] == "high"
    assert variables["webhook.source"] == "operations-monitor"
    assert "status.example" in variables["webhook.reference"]
    assert "incident" in variables["webhook.tags"]
    assert "Incident acknowledged" in variables["webhook.raw"]


def test_https_post_webhook_receiver_handles_nested_payloads():
    payload = {
        "event": {
            "id": "evt-200",
            "type": "status.change",
            "time": "2025-02-02T09:30:00Z",
            "detail": {
                "title": "Ticket updated",
                "description": "Ticket moved to investigating",
                "user": {"name": "Alex"},
            },
        },
        "metadata": {
            "links": {"permalink": "https://tickets.example/tk-123"},
            "labels": ["ticket", "update"],
        },
    }

    with TestClient(app) as client:
        response = client.post("/api/webhooks/https-post", json=payload)

    assert response.status_code == 200
    variables = response.json()["variables"]
    assert variables["webhook.id"] == "evt-200"
    assert variables["webhook.type"] == "status.change"
    assert variables["webhook.summary"] == "Ticket updated"
    assert variables["webhook.actor"] == "Alex"
    assert variables["webhook.reference"].endswith("tk-123")
    assert "ticket" in variables["webhook.tags"]


def test_https_post_webhook_receiver_counts_collections():
    payload = {
        "records": [
            {"id": 1, "name": "CPU"},
            {"id": 2, "name": "Memory"},
        ],
        "details": "Multiple resources breached thresholds.",
    }

    with TestClient(app) as client:
        response = client.post("/api/webhooks/https-post", json=payload)

    assert response.status_code == 200
    variables = response.json()["variables"]
    assert variables["webhook.attachments_count"] == "2"
    assert variables["webhook.details"] == "Multiple resources breached thresholds."


def test_https_post_webhook_triggers_automation(monkeypatch):
    asyncio.run(_create_https_post_automation())

    captured: dict[str, object] = {}

    async def fake_ntfy(session, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.services.automation_events.send_ntfy_notification",
        fake_ntfy,
    )

    payload = {
        "id": "evt-300",
        "summary": "Intrusion detected",
        "severity": "critical",
    }

    with TestClient(app) as client:
        response = client.post("/api/webhooks/https-post", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    variables = body["variables"]
    assert variables["webhook.summary"] == "Intrusion detected"
    assert captured["message"] == "Webhook summary: Intrusion detected"
    assert captured["automation_name"] == "Webhook responder"
    assert captured["event_type"] == "HTTP POST Webhook Received"
    assert captured["ticket_identifier"] == "unknown"
