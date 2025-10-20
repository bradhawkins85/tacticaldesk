import asyncio
from datetime import datetime, timezone

import pytest

import httpx
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.core.tickets import ticket_store
from app.models import IntegrationModule
from app.services.ticket_summary import refresh_ticket_summary


@pytest.fixture(autouse=True)
def configure_database(tmp_path, monkeypatch):
    db_path = tmp_path / "ticket_summary.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    asyncio.run(dispose_engine())
    yield
    asyncio.run(dispose_engine())
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_ticket_store():
    asyncio.run(ticket_store.reset())
    yield
    asyncio.run(ticket_store.reset())


class _DummyResponse:
    def raise_for_status(self) -> None:  # pragma: no cover - simple stub
        return None

    def json(self) -> dict[str, str]:
        return {
            "response": json.dumps(
                {
                    "summary": "AI generated summary emphasising resolution status.",
                    "resolution_status": "resolved",
                }
            )
        }


class _DummyAsyncClient:
    last_request: dict[str, object] | None = None

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, endpoint, *, json):
        _DummyAsyncClient.last_request = {"endpoint": endpoint, "json": json}
        return _DummyResponse()


@pytest.mark.asyncio
async def test_refresh_ticket_summary_uses_fallback_when_module_disabled():
    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        module = (
            await session.execute(
                select(IntegrationModule).where(IntegrationModule.slug == "ollama")
            )
        ).scalar_one()
        module.enabled = False
        await session.commit()

        ticket = {
            "id": "TD-9001",
            "subject": "Wi-Fi outage at HQ",
            "customer": "Quest Logistics",
            "customer_email": "netops@quest-logistics.example",
            "status": "Open",
            "priority": "Critical",
            "team": "Tier 2",
            "assignment": "On-call engineer",
            "queue": "Incident response",
            "category": "Incident",
            "summary": "All SSIDs at headquarters are offline after overnight maintenance.",
            "history": [],
        }

        record = await refresh_ticket_summary(session, ticket)

    assert record is not None
    assert record["provider"] == "fallback"
    assert "Latest update" in record["summary"]
    assert record["error_message"] == "Ollama module is disabled."
    assert record["resolution_state"] == "in_progress"

    stored = await ticket_store.get_summary("TD-9001")
    assert stored is not None
    assert stored["provider"] == "fallback"
    assert stored["resolution_state"] == "in_progress"


@pytest.mark.asyncio
async def test_refresh_ticket_summary_invokes_ollama_when_enabled(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _DummyAsyncClient)

    engine = await get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        module = (
            await session.execute(
                select(IntegrationModule).where(IntegrationModule.slug == "ollama")
            )
        ).scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "base_url": "http://ollama.internal",
                "model": "llama3.1",
                "prompt": "Highlight mitigation owners.",
            }
        )
        await session.commit()

        ticket = {
            "id": "TD-9002",
            "subject": "Firewall failover alert",
            "customer": "Quest Logistics",
            "status": "Investigating",
            "priority": "High",
            "team": "Security",
            "assignment": "SOC",
            "queue": "Security incidents",
            "category": "Security",
            "summary": "Failover triggered for primary firewall cluster; traffic on backup node.",
            "history": [
                {
                    "actor": "Automation",
                    "channel": "Monitoring",
                    "summary": "Received SNMP trap indicating failover event.",
                    "timestamp_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            ],
        }

        record = await refresh_ticket_summary(session, ticket)

    assert record is not None
    assert record["provider"] == "ollama"
    assert record["summary"] == "AI generated summary emphasising resolution status."
    assert record["model"] == "llama3.1"
    assert record["resolution_state"] == "resolved"

    captured = _DummyAsyncClient.last_request
    assert captured is not None
    assert captured["endpoint"].startswith("http://ollama.internal/")
    assert captured["json"]["model"] == "llama3.1"
