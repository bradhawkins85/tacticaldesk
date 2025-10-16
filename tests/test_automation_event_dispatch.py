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
