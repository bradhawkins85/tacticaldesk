import asyncio

import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.models import IntegrationModule
from app.services.notifications import send_ntfy_notification


@pytest.fixture(autouse=True)
def notifications_db(tmp_path, monkeypatch):
    db_path = tmp_path / "notifications.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    asyncio.run(dispose_engine())
    get_settings.cache_clear()


class _DummyResponse:
    def raise_for_status(self) -> None:  # pragma: no cover - simple stub
        return None


class _DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, endpoint, *, content, headers):
        _DummyAsyncClient.last_call = {
            "endpoint": endpoint,
            "content": content,
            "headers": headers,
        }
        return _DummyResponse()


@pytest.mark.asyncio
async def test_send_ntfy_notification_sanitizes_headers(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _DummyAsyncClient)
    engine = await get_engine()

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "ntfy")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "base_url": "https://ntfy.example",
                "topic": "alerts",
                "token": "secret-token",
            }
        )
        await session.commit()

        await send_ntfy_notification(
            session,
            message="Ticket assigned to — responder",
            automation_name="Äuto — Name",
            event_type="Créated — ✨",
            ticket_identifier="TK-∞",
        )

    captured = getattr(_DummyAsyncClient, "last_call")
    assert captured["endpoint"] == "https://ntfy.example/alerts"
    assert captured["content"] == "Ticket assigned to — responder".encode("utf-8")

    headers = captured["headers"]
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["Authorization"] == "Bearer secret-token"

    for value in headers.values():
        assert isinstance(value, str)
        value.encode("ascii")

    assert headers["Title"] == "Auto - Name - Created -"
    assert headers["X-TacticalDesk-Automation"] == "Auto - Name"
    assert headers["X-TacticalDesk-Ticket"] == "TK-"


@pytest.mark.asyncio
async def test_send_ntfy_notification_prefers_topic_override(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _DummyAsyncClient)
    engine = await get_engine()

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "ntfy")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "base_url": "https://ntfy.example",
                "topic": "default-topic",
            }
        )
        await session.commit()

        await send_ntfy_notification(
            session,
            message="Ticket escalated",
            automation_name="Escalation",
            event_type="Ticket Created",
            ticket_identifier="TK-123",
            topic_override="  override-topic  ",
        )

    captured = getattr(_DummyAsyncClient, "last_call")
    assert captured["endpoint"] == "https://ntfy.example/override-topic"
