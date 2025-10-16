from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.main import app
from app.models import WebhookDelivery, utcnow


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
