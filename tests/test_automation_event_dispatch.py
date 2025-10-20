import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.models import Automation
from app.services.automation_events import dispatch_ticket_event


@pytest.fixture(autouse=True)
def automation_dispatch_db(tmp_path, monkeypatch):
    db_path = tmp_path / "automation-events.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("TACTICAL_DESK_ENABLE_INSTALLERS", "0")
    get_settings.cache_clear()
    yield
    asyncio.run(dispose_engine())
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dispatch_invokes_ntfy_notification(monkeypatch):
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        automation = Automation(
            name="Ntfy responder",
            description="Send ntfy notification",
            playbook="Alerting",
            kind="event",
            trigger="Ticket Created",
            ticket_actions=[
                {
                    "action": "send-ntfy-notification",
                    "value": "Ticket {{ ticket.id }} assigned to {{ ticket.assignment }}.",
                    "topic": "{{ ticket.assignment }}",
                }
            ],
        )
        session.add(automation)
        await session.commit()

        captured: dict[str, object] = {}

        async def fake_ntfy(session_arg, **kwargs):
            captured["session"] = session_arg
            captured.update(kwargs)

        monkeypatch.setattr(
            "app.services.automation_events.send_ntfy_notification",
            fake_ntfy,
        )

        await dispatch_ticket_event(
            session,
            event_type="Ticket Created",
            ticket_after={"id": 501, "assignment": "Duty Officer"},
        )

        assert captured["message"] == "Ticket 501 assigned to Duty Officer."
        assert captured["automation_name"] == "Ntfy responder"
        assert captured["event_type"] == "Ticket Created"
        assert captured["ticket_identifier"] == "501"
        assert captured["topic_override"] == "Duty Officer"


@pytest.mark.asyncio
async def test_dispatch_invokes_smtp_with_recipients(monkeypatch):
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        automation = Automation(
            name="SMTP responder",
            description="Send smtp notification",
            playbook="Alerting",
            kind="event",
            trigger="Ticket Created",
            ticket_actions=[
                {
                    "action": "send-smtp-email",
                    "value": "Ticket {{ ticket.id }} escalated.",
                    "topic": "Escalation {{ ticket.id }}",
                    "to_recipients": "ops@example.com",
                    "cc_recipients": "lead@example.com",
                }
            ],
        )
        session.add(automation)
        await session.commit()

        captured: dict[str, object] = {}

        async def fake_smtp(session_arg, **kwargs):
            captured["session"] = session_arg
            captured.update(kwargs)

        monkeypatch.setattr(
            "app.services.automation_events.send_smtp_email",
            fake_smtp,
        )

        await dispatch_ticket_event(
            session,
            event_type="Ticket Created",
            ticket_after={"id": 777},
        )

        assert captured["to"] == "ops@example.com"
        assert captured["cc"] == "lead@example.com"
        assert captured["subject"] == "Escalation 777"
        assert captured["automation_name"] == "SMTP responder"


@pytest.mark.asyncio
async def test_dispatch_applies_regex_operator():
    engine = await get_engine()
    async with AsyncSession(engine) as session:
        automation = Automation(
            name="Regex watcher",
            description="Matches regex subjects",
            playbook="Alerting",
            kind="event",
            trigger="Ticket Updated by Technician",
            trigger_filters={
                "match": "all",
                "conditions": [
                    {
                        "type": "Ticket Subject",
                        "operator": "matches_regex",
                        "value": r"^Server \d+ Down$",
                    }
                ],
            },
        )
        session.add(automation)
        await session.commit()

        untriggered = await dispatch_ticket_event(
            session,
            event_type="Ticket Updated by Technician",
            ticket_after={"id": 200, "subject": "Service Outage"},
        )
        assert not untriggered

        triggered = await dispatch_ticket_event(
            session,
            event_type="Ticket Updated by Technician",
            ticket_after={"id": 201, "subject": "server 42 down"},
        )
        assert triggered
        assert triggered[0] is automation
