import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import MockTransport, Request, Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.tickets import ticket_store
from app.models import IntegrationModule, Organization
from app.services.syncro import (
    SyncroConfigurationError,
    SyncroTicketImportOptions,
    fetch_syncro_companies,
    import_syncro_companies,
    import_syncro_data,
)
from app.services.ticket_data import fetch_ticket_records


@pytest.fixture(autouse=True)
def _configure_database(tmp_path, monkeypatch):
    asyncio.run(dispose_engine())
    db_path = tmp_path / "syncro.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    asyncio.run(dispose_engine())


@pytest_asyncio.fixture(autouse=True)
async def _reset_ticket_store():
    await ticket_store.reset()
    yield
    await ticket_store.reset()


def _mock_syncro_transport() -> MockTransport:
    def handler(request: Request) -> Response:
        assert request.headers.get("Authorization") == "Bearer test-key"
        if request.url.path.endswith("/api/v1/customers"):
            return Response(
                200,
                json={
                    "customers": [
                        {
                            "id": 42,
                            "business_name": "Acme Corp",
                            "primary_contact": {"email": "it@acme.test"},
                            "notes": "Priority customer",
                        },
                        {
                            "id": 77,
                            "business_name": "Globex",
                            "primary_contact": {"email": "admin@globex.test"},
                        },
                    ],
                    "meta": {"total_pages": 1},
                },
            )
        if request.url.path.endswith("/api/v1/tickets"):
            return Response(
                200,
                json={
                    "tickets": [
                        {
                            "id": 1001,
                            "subject": "Printer offline",
                            "status": "Open",
                            "priority": "High",
                            "customer": {"business_name": "Acme Corp"},
                            "customer_email": "ops@acme.test",
                            "updated_at": "2024-05-02T12:00:00Z",
                            "created_at": "2024-05-01T09:00:00Z",
                            "due_date": "2024-05-03T12:00:00Z",
                            "tags": ["Hardware", "Printer"],
                            "cc_emails": ["lead@acme.test", "lead@acme.test"],
                            "assigned_tech_name": "Jordan Smith",
                            "queue_name": "Support",
                            "type": "Incident",
                            "description": "Office printer offline",
                        },
                        {
                            "id": 1002,
                            "number": "TD-1002",
                            "subject": "Laptop battery issue",
                            "status": "Closed",
                            "priority": "Low",
                            "customer": {"business_name": "Globex"},
                            "customer_email": "support@globex.test",
                            "updated_at": "2024-04-01T08:00:00Z",
                            "created_at": "2024-03-31T15:30:00Z",
                            "tags": [],
                            "assigned_to": "Alex Johnson",
                            "queue_name": "Hardware",
                            "type": "Request",
                            "description": "Battery drains quickly",
                        },
                    ],
                    "meta": {"total_pages": 1},
                },
            )
        if request.url.path.endswith("/api/v1/tickets/1001"):
            return Response(
                200,
                json={
                    "ticket": {
                        "id": 1001,
                        "subject": "Printer offline",
                        "status": "Open",
                        "priority": "High",
                        "customer": {"business_name": "Acme Corp"},
                        "customer_email": "ops@acme.test",
                        "updated_at": "2024-05-02T12:00:00Z",
                        "created_at": "2024-05-01T09:00:00Z",
                        "due_date": "2024-05-03T12:00:00Z",
                        "tags": ["Hardware", "Printer"],
                        "cc_emails": ["lead@acme.test", "lead@acme.test"],
                        "assigned_tech_name": "Jordan Smith",
                        "queue_name": "Support",
                        "type": "Incident",
                        "description": "Office printer offline",
                    }
                },
            )
        if request.url.path.endswith("/api/v1/tickets/1002"):
            return Response(
                200,
                json={
                    "ticket": {
                        "id": 1002,
                        "number": "TD-1002",
                        "subject": "Laptop battery issue",
                        "status": "Closed",
                        "priority": "Low",
                        "customer": {"business_name": "Globex"},
                        "customer_email": "support@globex.test",
                        "updated_at": "2024-04-01T08:00:00Z",
                        "created_at": "2024-03-31T15:30:00Z",
                        "tags": [],
                        "assigned_to": "Alex Johnson",
                        "queue_name": "Hardware",
                        "type": "Request",
                        "description": "Battery drains quickly",
                    }
                },
            )
        return Response(404, json={"detail": "not found"})

    return MockTransport(handler)


@pytest.mark.asyncio
async def test_syncro_import_creates_companies_and_tickets():
    transport = _mock_syncro_transport()
    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "subdomain": "syncro",
                "api_key": "test-key",
            }
        )
        await session.commit()

        summary = await import_syncro_data(
            session,
            company_ids=[42],
            ticket_options=SyncroTicketImportOptions(mode="single", ticket_number=1001),
            transport=transport,
            throttle_seconds=0,
        )
        assert summary.companies_created == 1
        assert summary.companies_updated == 0
        assert summary.tickets_imported == 1
        assert summary.tickets_skipped == 0

        org_result = await session.execute(
            select(Organization).where(Organization.slug == "acme-corp")
        )
        organization = org_result.scalar_one_or_none()
        assert organization is not None
        assert organization.contact_email == "it@acme.test"

        globex_result = await session.execute(
            select(Organization).where(Organization.slug == "globex")
        )
        assert globex_result.scalar_one_or_none() is None

    now = datetime.now(timezone.utc)
    records = await fetch_ticket_records(now)
    ids = {ticket["id"] for ticket in records}
    assert "SYNCRO-1001" in ids
    ticket = next(ticket for ticket in records if ticket["id"] == "SYNCRO-1001")
    assert ticket["customer"] == "Acme Corp"
    assert ticket["queue"] == "Support"
    assert ticket["labels"] == ["Hardware", "Printer"]
    assert ticket["watchers"] == ["lead@acme.test"]
    assert "SYNCRO-1002" not in ids


@pytest.mark.asyncio
async def test_syncro_company_import_only_creates_companies():
    transport = _mock_syncro_transport()
    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "subdomain": "syncro",
                "api_key": "test-key",
            }
        )
        await session.commit()

        summary = await import_syncro_companies(
            session,
            company_ids=[42, 77],
            transport=transport,
            throttle_seconds=0,
        )

        assert summary.companies_created == 2
        assert summary.companies_updated == 0
        assert summary.tickets_imported == 0
        assert summary.tickets_skipped == 0

        for slug in ("acme-corp", "globex"):
            result = await session.execute(
                select(Organization).where(Organization.slug == slug)
            )
            organization = result.scalar_one_or_none()
            assert organization is not None
            assert organization.is_archived is False

    now = datetime.now(timezone.utc)
    records = await fetch_ticket_records(now)
    assert not any(record["id"].startswith("SYNCRO-") for record in records)


@pytest.mark.asyncio
async def test_syncro_import_requires_configuration():
    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = False
        await session.commit()

        with pytest.raises(SyncroConfigurationError):
            await import_syncro_data(session)


@pytest.mark.asyncio
async def test_syncro_import_uses_ticket_endpoint_for_unknown_mode():
    calls: list[str] = []

    def handler(request: Request) -> Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/api/v1/customers"):
            return Response(
                200,
                json={"customers": [], "meta": {"total_pages": 1}},
            )
        if request.url.path.endswith("/api/v1/tickets"):
            return Response(
                200,
                json={"tickets": [], "meta": {"total_pages": 1}},
            )
        return Response(404, json={"detail": "unexpected endpoint"})

    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "subdomain": "syncro",
                "api_key": "test-key",
            }
        )
        await session.commit()

        summary = await import_syncro_data(
            session,
            ticket_options=SyncroTicketImportOptions(mode="invalid"),
            transport=MockTransport(handler),
            throttle_seconds=0,
        )

    assert any(path.endswith("/api/v1/tickets") for path in calls)
    assert summary.tickets_imported == 0
    assert summary.tickets_skipped == 0


@pytest.mark.asyncio
async def test_syncro_import_supports_ticket_range_and_company_selection():
    transport = _mock_syncro_transport()
    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "subdomain": "syncro",
                "api_key": "test-key",
            }
        )
        await session.commit()

        summary = await import_syncro_data(
            session,
            company_ids=[42, 77],
            ticket_options=SyncroTicketImportOptions(
                mode="range", range_start=1001, range_end=1002
            ),
            transport=transport,
            throttle_seconds=0,
        )

        assert summary.tickets_imported == 2

        for slug in ("acme-corp", "globex"):
            result = await session.execute(
                select(Organization).where(Organization.slug == slug)
            )
            assert result.scalar_one_or_none() is not None

    now = datetime.now(timezone.utc)
    records = await fetch_ticket_records(now)
    ids = {ticket["id"] for ticket in records}
    assert "SYNCRO-1001" in ids
    assert "SYNCRO-1002" in ids

    ticket = next(ticket for ticket in records if ticket["id"] == "SYNCRO-1002")
    assert ticket["customer"] == "Globex"
    assert ticket["assignment"] == "Alex Johnson"
    assert ticket["id"] == "SYNCRO-1002"


@pytest.mark.asyncio
async def test_fetch_syncro_companies_returns_normalized_records():
    transport = _mock_syncro_transport()
    session_factory = await get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "syncro-rmm")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "subdomain": "syncro",
                "api_key": "test-key",
            }
        )
        await session.commit()

        companies = await fetch_syncro_companies(
            session, transport=transport, throttle_seconds=0
        )

    assert {company.external_id for company in companies} == {42, 77}
    acme = next(company for company in companies if company.external_id == 42)
    assert acme.slug == "acme-corp"

