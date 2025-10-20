import asyncio

import asyncio
from typing import Any

import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.models import IntegrationModule
from app.services.notifications import send_ntfy_notification, send_smtp_email


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


class _DummySMTP:
    last_kwargs: dict[str, Any] | None = None
    send_calls: list[dict[str, Any]] = []
    login_args: tuple[str, str] | None = None
    starttls_called: bool = False
    connected: bool = False
    quit_called: bool = False

    def __init__(self, *, host=None, port=None, timeout=None, context=None, **kwargs):
        _DummySMTP.last_kwargs = {
            "host": host,
            "port": port,
            "timeout": timeout,
        }
        if context is not None:
            _DummySMTP.last_kwargs["context"] = context

    def __enter__(self):
        _DummySMTP.connected = True
        return self

    def __exit__(self, exc_type, exc, tb):
        _DummySMTP.quit_called = True
        return False

    def ehlo(self):
        return None

    def starttls(self, *, context=None):
        _DummySMTP.starttls_called = True
        _DummySMTP.last_kwargs["starttls_context"] = context

    def login(self, username, password):
        _DummySMTP.login_args = (username, password)

    def send_message(self, message, from_addr, to_addrs):
        _DummySMTP.send_calls.append(
            {
                "message": message,
                "sender": from_addr,
                "recipients": list(to_addrs),
            }
        )
        return {}

    @classmethod
    def reset(cls):
        cls.last_kwargs = None
        cls.send_calls = []
        cls.login_args = None
        cls.starttls_called = False
        cls.connected = False
        cls.quit_called = False


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


@pytest.mark.asyncio
async def test_send_smtp_email_skips_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.notifications.smtplib.SMTP", _DummySMTP)
    monkeypatch.setattr("app.services.notifications.smtplib.SMTP_SSL", _DummySMTP)
    _DummySMTP.reset()

    engine = await get_engine()

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "smtp-email")
        )
        module = result.scalar_one()
        module.enabled = False
        module.settings.update(
            {
                "smtp_host": "smtp.example.com",
                "smtp_sender": "alerts@example.com",
            }
        )
        await session.commit()

        await send_smtp_email(
            session,
            subject="Alert",
            body="Ticket assigned",
            automation_name="Assignment",
            event_type="Ticket Created",
            ticket_identifier="TK-100",
            to="team@example.com",
        )

    assert _DummySMTP.send_calls == []
    assert _DummySMTP.connected is False


@pytest.mark.asyncio
async def test_send_smtp_email_uses_module_configuration(monkeypatch):
    monkeypatch.setattr("app.services.notifications.smtplib.SMTP", _DummySMTP)
    monkeypatch.setattr("app.services.notifications.smtplib.SMTP_SSL", _DummySMTP)
    _DummySMTP.reset()

    engine = await get_engine()

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(IntegrationModule).where(IntegrationModule.slug == "smtp-email")
        )
        module = result.scalar_one()
        module.enabled = True
        module.settings.update(
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 2525,
                "smtp_username": "mailer",
                "smtp_password": "SecretPass123",
                "smtp_sender": "alerts@example.com",
                "smtp_bcc": "audit@example.com",
                "smtp_use_tls": "true",
                "smtp_use_ssl": "false",
            }
        )
        await session.commit()

        await send_smtp_email(
            session,
            subject="Incident escalated",
            body="Ticket TK-200 escalated",
            automation_name="Escalation",
            event_type="Ticket Updated",
            ticket_identifier="TK-200",
            to="oncall@example.com, team@example.com",
            cc="lead@example.com",
        )

    assert _DummySMTP.last_kwargs["host"] == "smtp.example.com"
    assert _DummySMTP.last_kwargs["port"] == 2525
    assert _DummySMTP.last_kwargs["timeout"] == 15.0
    assert "context" not in _DummySMTP.last_kwargs
    assert _DummySMTP.connected is True
    assert _DummySMTP.starttls_called is True
    assert _DummySMTP.login_args == ("mailer", "SecretPass123")
    assert _DummySMTP.quit_called is True
    assert len(_DummySMTP.send_calls) == 1

    call = _DummySMTP.send_calls[0]
    assert call["sender"] == "alerts@example.com"
    assert call["recipients"] == [
        "oncall@example.com",
        "team@example.com",
        "lead@example.com",
        "audit@example.com",
    ]
    message = call["message"]
    assert message["Subject"] == "Incident escalated"
    assert message["To"] == "oncall@example.com, team@example.com"
    assert message["Cc"] == "lead@example.com"
