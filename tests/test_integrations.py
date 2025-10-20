import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.main import app
from app.models import WebhookDelivery, utcnow


@pytest.fixture(autouse=True)
def integration_db(tmp_path, monkeypatch):
    db_path = tmp_path / "integrations.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _create_module_webhook(event_id: str, status: str = "retrying") -> None:
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        delivery = WebhookDelivery(
            event_id=event_id,
            endpoint="https://hooks.example/log",
            module_slug="syncro-rmm",
            request_method="GET",
            request_url="https://hooks.example/log",
            status=status,
            last_attempt_at=utcnow() - timedelta(minutes=5),
            next_retry_at=utcnow() + timedelta(minutes=10),
        )
        session.add(delivery)
        await session.commit()


async def _get_module_webhook(event_id: str) -> WebhookDelivery | None:
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(WebhookDelivery).where(WebhookDelivery.event_id == event_id)
        )
        return result.scalar_one_or_none()


def test_seeded_integrations_available():
    with TestClient(app) as client:
        response = client.get("/api/integrations")
        assert response.status_code == 200
        payload = response.json()
        slugs = {item["slug"] for item in payload}
        assert {
            "syncro-rmm",
            "tactical-rmm",
            "xero",
            "ntfy",
            "smtp-email",
            "https-post-receiver",
        }.issubset(slugs)
        status_map = {item["slug"]: item["enabled"] for item in payload}
        assert status_map["syncro-rmm"] is True
        assert status_map["tactical-rmm"] is True
        assert status_map["xero"] is False
        assert status_map["ntfy"] is False
        assert status_map["smtp-email"] is False
        assert status_map["https-post-receiver"] is False


def test_toggle_integration_updates_navigation():
    with TestClient(app) as client:
        disable_response = client.patch("/api/integrations/syncro-rmm", json={"enabled": False})
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False

        html_response = client.get("/integrations")
        assert html_response.status_code == 200
        html = html_response.text
        assert "SyncroRMM" in html
        assert 'data-integration-link="syncro-rmm"' not in html


def test_disabling_module_pauses_webhooks():
    asyncio.run(_create_module_webhook("whk-sync-1", status="retrying"))
    asyncio.run(_create_module_webhook("whk-sync-2", status="failed"))

    with TestClient(app) as client:
        response = client.patch("/api/integrations/syncro-rmm", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        delivery_one = asyncio.run(_get_module_webhook("whk-sync-1"))
        delivery_two = asyncio.run(_get_module_webhook("whk-sync-2"))
        assert delivery_one.status == "paused"
        assert delivery_two.status == "paused"
        assert delivery_one.next_retry_at is None

        reenable = client.patch("/api/integrations/syncro-rmm", json={"enabled": True})
        assert reenable.status_code == 200
        assert reenable.json()["enabled"] is True

        resumed_one = asyncio.run(_get_module_webhook("whk-sync-1"))
        resumed_two = asyncio.run(_get_module_webhook("whk-sync-2"))
        assert resumed_one.status == "retrying"
        assert resumed_two.status == "retrying"
        assert resumed_one.next_retry_at is not None

def test_update_integration_settings_reflected_in_detail():
    with TestClient(app) as client:
        payload = {
            "settings": {
                "subdomain": "syncro-example",
                "api_key": "SecureKey123",
            }
        }
        response = client.patch("/api/integrations/syncro-rmm", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["api_key"] == "SecureKey123"
        assert data["settings"]["subdomain"] == "syncro-example"

        detail_response = client.get("/integrations/syncro-rmm")
        assert detail_response.status_code == 200
        detail_html = detail_response.text
        assert "Syncro subdomain" in detail_html
        assert "syncro-example" in detail_html
        assert "SecureKey123" in detail_html


def test_ntfy_integration_fields_rendered():
    with TestClient(app) as client:
        detail_response = client.get("/integrations/ntfy")
        assert detail_response.status_code == 200
        html = detail_response.text
        assert "Base URL" in html
        assert "Topic" in html
        assert "Access token" in html


def test_smtp_integration_fields_rendered():
    with TestClient(app) as client:
        detail_response = client.get("/integrations/smtp-email")
        assert detail_response.status_code == 200
        html = detail_response.text
        assert "SMTP host" in html
        assert "From address" in html
        assert "BCC recipients" in html
        assert "Use STARTTLS" in html
        assert "Specify To and CC recipients" in html


def test_https_post_webhook_receiver_displays_endpoint_instead_of_form():
    with TestClient(app) as client:
        detail_response = client.get("/integrations/https-post-receiver")
        assert detail_response.status_code == 200
        html = detail_response.text
        assert "HTTPS POST webhook endpoint" in html
        assert "Accept HTTPS POST calls from any service" in html
        assert "http://testserver/api/webhooks/https-post" in html
        assert "curl -X POST" in html
        assert "integration-settings-form" not in html
