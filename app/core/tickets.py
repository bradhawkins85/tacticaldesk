from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Dict, Iterable, List, Set
import re
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


@dataclass
class StoredTicketRecord:
    id: str
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
    channel: str
    created_at_dt: datetime
    last_reply_dt: datetime
    due_at_dt: datetime | None
    labels: List[str]
    watchers: List[str]
    is_starred: bool
    assets_visible: bool
    history: List[dict[str, object]]
    metadata_created_at_dt: datetime
    metadata_updated_at_dt: datetime

    def as_ticket(self) -> dict[str, object]:
        return {
            "id": self.id,
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
            "channel": self.channel,
            "created_at_dt": self.created_at_dt,
            "last_reply_dt": self.last_reply_dt,
            "due_at_dt": self.due_at_dt,
            "labels": list(self.labels),
            "watchers": list(self.watchers),
            "is_starred": self.is_starred,
            "assets_visible": self.assets_visible,
            "history": [dict(entry) for entry in self.history],
            "metadata_created_at_dt": self.metadata_created_at_dt,
            "metadata_updated_at_dt": self.metadata_updated_at_dt,
        }


class TicketStore:
    """In-memory override store for seed ticket data."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._overrides: Dict[str, StoredTicketOverride] = {}
        self._replies: Dict[str, List[dict[str, object]]] = {}
        self._created: Dict[str, StoredTicketRecord] = {}
        self._sequence_floor = 5000
        self._ticket_sequence = self._sequence_floor
        self._deleted_customers: Set[str] = set()
        self._deleted_emails: Set[str] = set()

    def _normalized(self, value: str | None) -> str:
        if not value:
            return ""
        return value.strip().lower()

    def _is_deleted(self, customer: str | None, customer_email: str | None) -> bool:
        customer_key = self._normalized(customer)
        email_key = self._normalized(customer_email)
        if customer_key and customer_key in self._deleted_customers:
            return True
        if email_key and email_key in self._deleted_emails:
            return True
        return False

    def _extract_ticket_number(self, ticket_id: str) -> int:
        match = re.search(r"(\d+)$", ticket_id)
        if not match:
            return self._sequence_floor
        try:
            return int(match.group(1))
        except ValueError:
            return self._sequence_floor

    def _next_ticket_id(self, existing_ids: Iterable[str] | None = None) -> str:
        highest = self._ticket_sequence
        if existing_ids:
            for value in existing_ids:
                highest = max(highest, self._extract_ticket_number(value))
        for value in self._created:
            highest = max(highest, self._extract_ticket_number(value))
        for value in self._overrides:
            highest = max(highest, self._extract_ticket_number(value))
        self._ticket_sequence = max(highest, self._sequence_floor) + 1
        return f"TD-{self._ticket_sequence:04d}"

    async def apply_overrides(
        self, tickets: Iterable[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Merge any stored overrides into the provided ticket records."""
        async with self._lock:
            merged: list[dict[str, object]] = [
                record.as_ticket() for record in self._created.values()
            ]
            for ticket in tickets:
                override = self._overrides.get(ticket["id"])  # type: ignore[index]
                if override is None:
                    merged.append(dict(ticket))
                    continue
                merged.append({**ticket, **override.as_dict()})
            filtered: list[dict[str, object]] = []
            for ticket in merged:
                customer = ticket.get("customer")
                customer_email = ticket.get("customer_email")
                if self._is_deleted(
                    customer if isinstance(customer, str) else None,
                    customer_email if isinstance(customer_email, str) else None,
                ):
                    continue
                filtered.append(ticket)
            return filtered

    async def get_override(self, ticket_id: str) -> dict[str, object] | None:
        async with self._lock:
            created = self._created.get(ticket_id)
            if created is not None:
                return created.as_ticket()
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
            now = utcnow()
            if ticket_id in self._created:
                record = self._created[ticket_id]
                record.subject = subject
                record.customer = customer
                record.customer_email = customer_email
                record.status = status
                record.priority = priority
                record.team = team
                record.assignment = assignment
                record.queue = queue
                record.category = category
                record.summary = summary
                record.metadata_updated_at_dt = now
                record.last_reply_dt = now
                self._created[ticket_id] = record
                return record.as_ticket()

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
                metadata_updated_at_dt=now,
            )
            self._overrides[ticket_id] = override
            return override.as_dict()

    async def create_ticket(
        self,
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
        existing_ids: Iterable[str] | None = None,
    ) -> dict[str, object]:
        """Create a new ticket entry and persist it for future lookups."""

        async with self._lock:
            ticket_id = self._next_ticket_id(existing_ids)
            now = utcnow()
            due_at = now + timedelta(days=2)
            record = StoredTicketRecord(
                id=ticket_id,
                subject=subject.strip(),
                customer=customer.strip(),
                customer_email=customer_email.strip(),
                status=status.strip(),
                priority=priority.strip(),
                team=team.strip(),
                assignment=assignment.strip(),
                queue=queue.strip(),
                category=category.strip(),
                summary=summary.strip(),
                channel="Portal",
                created_at_dt=now,
                last_reply_dt=now,
                due_at_dt=due_at,
                labels=[],
                watchers=[],
                is_starred=False,
                assets_visible=False,
                history=[],
                metadata_created_at_dt=now,
                metadata_updated_at_dt=now,
            )
            self._created[ticket_id] = record
            return record.as_ticket()

    async def append_reply(
        self,
        ticket_id: str,
        *,
        actor: str,
        channel: str,
        summary: str,
        message: str,
    ) -> dict[str, object]:
        """Store a reply entry for the ticket conversation history."""

        async with self._lock:
            reply_entry = {
                "actor": actor,
                "direction": "outbound",
                "channel": channel,
                "summary": summary,
                "body": escape(message),
                "timestamp_dt": utcnow(),
            }
            existing = self._replies.setdefault(ticket_id, [])
            existing.append(reply_entry)
            return dict(reply_entry)

    async def list_replies(self, ticket_id: str) -> list[dict[str, object]]:
        async with self._lock:
            replies = self._replies.get(ticket_id, [])
            return [dict(entry) for entry in replies]

    async def reset(self) -> None:
        """Clear overrides (useful for tests)."""
        async with self._lock:
            self._overrides.clear()
            self._replies.clear()
            self._created.clear()
            self._ticket_sequence = self._sequence_floor
            self._deleted_customers.clear()
            self._deleted_emails.clear()

    async def delete_tickets_for_organization(
        self,
        *,
        organization_name: str,
        contact_emails: Iterable[str] | None = None,
    ) -> None:
        """Remove tickets tied to the provided organization metadata."""
        async with self._lock:
            normalized_name = self._normalized(organization_name)
            if normalized_name:
                self._deleted_customers.add(normalized_name)

            normalized_emails: Set[str] = set()
            for email in contact_emails or []:
                normalized = self._normalized(email)
                if normalized:
                    normalized_emails.add(normalized)
            self._deleted_emails.update(normalized_emails)

            for ticket_id, record in list(self._created.items()):
                if self._is_deleted(record.customer, record.customer_email):
                    self._created.pop(ticket_id, None)
                    self._replies.pop(ticket_id, None)

            for ticket_id, override in list(self._overrides.items()):
                if self._is_deleted(override.customer, override.customer_email):
                    self._overrides.pop(ticket_id, None)
                    self._replies.pop(ticket_id, None)


ticket_store = TicketStore()
