"""Automation event dispatcher for in-app triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import asyncio

from app.models import utcnow


@dataclass
class AutomationEvent:
    """Represents a dispatched automation trigger."""

    event_type: str
    ticket_id: str
    payload: Dict[str, Any]
    created_at: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "ticket_id": self.ticket_id,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }


class AutomationDispatcher:
    """In-memory automation dispatcher for testability."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._events: List[AutomationEvent] = []

    async def dispatch(
        self,
        *,
        event_type: str,
        ticket_id: str,
        payload: Dict[str, Any] | None = None,
    ) -> AutomationEvent:
        """Record a dispatched automation trigger event."""

        async with self._lock:
            event = AutomationEvent(
                event_type=event_type,
                ticket_id=ticket_id,
                payload=dict(payload or {}),
                created_at=utcnow(),
            )
            self._events.append(event)
            return event

    async def list_events(self) -> list[AutomationEvent]:
        async with self._lock:
            return list(self._events)

    async def reset(self) -> None:
        async with self._lock:
            self._events.clear()


automation_dispatcher = AutomationDispatcher()

