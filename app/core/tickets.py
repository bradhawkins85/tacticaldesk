from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable
import asyncio

from app.models import utcnow


@dataclass
class StoredTicketOverride:
    subject: str
    customer: str
    customer_email: str
    status: str
    priority: str
    team: str
    assignment: str
    queue: str
    category: str
    summary: str
    metadata_updated_at_dt: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "customer": self.customer,
            "customer_email": self.customer_email,
            "status": self.status,
            "priority": self.priority,
            "team": self.team,
            "assignment": self.assignment,
            "queue": self.queue,
            "category": self.category,
            "summary": self.summary,
            "metadata_updated_at_dt": self.metadata_updated_at_dt,
        }


class TicketStore:
    """In-memory override store for seed ticket data."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._overrides: Dict[str, StoredTicketOverride] = {}

    async def apply_overrides(
        self, tickets: Iterable[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Merge any stored overrides into the provided ticket records."""
        async with self._lock:
            merged: list[dict[str, object]] = []
            for ticket in tickets:
                override = self._overrides.get(ticket["id"])  # type: ignore[index]
                if override is None:
                    merged.append(dict(ticket))
                    continue
                merged.append({**ticket, **override.as_dict()})
            return merged

    async def get_override(self, ticket_id: str) -> dict[str, object] | None:
        async with self._lock:
            override = self._overrides.get(ticket_id)
            return override.as_dict() if override else None

    async def update_ticket(
        self,
        ticket_id: str,
        *,
        subject: str,
        customer: str,
        customer_email: str,
        status: str,
        priority: str,
        team: str,
        assignment: str,
        queue: str,
        category: str,
        summary: str,
    ) -> dict[str, object]:
        """Persist sanitized ticket updates for subsequent requests."""
        async with self._lock:
            override = StoredTicketOverride(
                subject=subject,
                customer=customer,
                customer_email=customer_email,
                status=status,
                priority=priority,
                team=team,
                assignment=assignment,
                queue=queue,
                category=category,
                summary=summary,
                metadata_updated_at_dt=utcnow(),
            )
            self._overrides[ticket_id] = override
            return override.as_dict()

    async def reset(self) -> None:
        """Clear overrides (useful for tests)."""
        async with self._lock:
            self._overrides.clear()


ticket_store = TicketStore()
