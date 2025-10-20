from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Dict, Iterable, List, Sequence, Set

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.db import get_session_factory
from app.models import (
    Ticket,
    TicketDeletion,
    TicketOverride,
    TicketReply,
    TicketSummary,
    utcnow,
)


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


@dataclass
class StoredTicketSummary:
    ticket_id: str
    provider: str
    model: str | None
    summary: str | None
    error_message: str | None
    updated_at_dt: datetime

    def as_dict(self) -> dict[str, object]:
        updated = self.updated_at_dt
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        updated_iso = updated.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "ticket_id": self.ticket_id,
            "provider": self.provider,
            "model": self.model,
            "summary": self.summary,
            "error_message": self.error_message,
            "updated_at_dt": updated,
            "updated_at_iso": updated_iso,
        }


class TicketStore:
    """Persistent ticket store that augments seed ticket data."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session_factory: sessionmaker[AsyncSession] | None = None
        self._external_sources: Dict[str, Dict[str, StoredTicketRecord]] = {}
        self._sequence_floor = 5000
        self._ticket_sequence = self._sequence_floor

    async def _ensure_session_factory(self) -> sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = await get_session_factory()
        return self._session_factory

    def _normalized(self, value: str | None) -> str:
        if not value:
            return ""
        return value.strip().lower()

    def _is_deleted(
        self,
        customer: str | None,
        customer_email: str | None,
        *,
        deleted_customers: Set[str],
        deleted_emails: Set[str],
    ) -> bool:
        customer_key = self._normalized(customer)
        email_key = self._normalized(customer_email)
        if customer_key and customer_key in deleted_customers:
            return True
        if email_key and email_key in deleted_emails:
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

    async def _next_ticket_id(
        self,
        session: AsyncSession,
        existing_ids: Iterable[str] | None = None,
    ) -> str:
        highest = self._ticket_sequence
        if existing_ids:
            for value in existing_ids:
                highest = max(highest, self._extract_ticket_number(value))

        created_ids = await session.execute(select(Ticket.id))
        for value, in created_ids:
            highest = max(highest, self._extract_ticket_number(value))

        override_ids = await session.execute(select(TicketOverride.ticket_id))
        for value, in override_ids:
            highest = max(highest, self._extract_ticket_number(value))

        for records in self._external_sources.values():
            for value in records:
                highest = max(highest, self._extract_ticket_number(value))

        self._ticket_sequence = max(highest, self._sequence_floor) + 1
        return f"TD-{self._ticket_sequence:04d}"

    def _record_from_model(self, model: Ticket) -> StoredTicketRecord:
        return StoredTicketRecord(
            id=model.id,
            subject=model.subject,
            customer=model.customer,
            customer_email=model.customer_email,
            status=model.status,
            priority=model.priority,
            team=model.team,
            assignment=model.assignment,
            queue=model.queue,
            category=model.category,
            summary=model.summary,
            channel=model.channel,
            created_at_dt=model.created_at_dt,
            last_reply_dt=model.last_reply_dt,
            due_at_dt=model.due_at_dt,
            labels=list(model.labels or []),
            watchers=list(model.watchers or []),
            is_starred=bool(model.is_starred),
            assets_visible=bool(model.assets_visible),
            history=[dict(entry) for entry in model.history or []],
            metadata_created_at_dt=model.metadata_created_at_dt,
            metadata_updated_at_dt=model.metadata_updated_at_dt,
        )

    def _override_from_model(self, model: TicketOverride) -> StoredTicketOverride:
        return StoredTicketOverride(
            subject=model.subject,
            customer=model.customer,
            customer_email=model.customer_email,
            status=model.status,
            priority=model.priority,
            team=model.team,
            assignment=model.assignment,
            queue=model.queue,
            category=model.category,
            summary=model.summary,
            metadata_updated_at_dt=model.metadata_updated_at_dt,
        )

    def _reply_to_dict(self, reply: TicketReply) -> dict[str, object]:
        return {
            "actor": reply.actor,
            "direction": reply.direction,
            "channel": reply.channel,
            "summary": reply.summary,
            "body": reply.body,
            "timestamp_dt": reply.timestamp_dt,
        }

    def _summary_from_model(self, model: TicketSummary) -> StoredTicketSummary:
        return StoredTicketSummary(
            ticket_id=model.ticket_id,
            provider=model.provider,
            model=model.model,
            summary=model.summary,
            error_message=model.error_message,
            updated_at_dt=model.updated_at_dt,
        )

    async def apply_overrides(
        self, tickets: Iterable[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Merge any stored overrides into the provided ticket records."""

        async with self._lock:
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                created_models = (
                    await session.execute(select(Ticket))
                ).scalars().all()
                created_records = [
                    self._record_from_model(model) for model in created_models
                ]
                override_models = (
                    await session.execute(select(TicketOverride))
                ).scalars().all()
                overrides = {
                    override.ticket_id: self._override_from_model(override)
                    for override in override_models
                }
                deletion_rows = await session.execute(
                    select(TicketDeletion.kind, TicketDeletion.value)
                )
                deleted_customers: Set[str] = set()
                deleted_emails: Set[str] = set()
                for kind, value in deletion_rows:
                    if kind == "customer":
                        deleted_customers.add(value)
                    elif kind == "email":
                        deleted_emails.add(value)

            merged: list[dict[str, object]] = [
                record.as_ticket() for record in created_records
            ]

            for records in self._external_sources.values():
                merged.extend(record.as_ticket() for record in records.values())

            for ticket in tickets:
                ticket_id = ticket.get("id")
                override = (
                    overrides.get(str(ticket_id))
                    if ticket_id is not None
                    else None
                )
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
                    deleted_customers=deleted_customers,
                    deleted_emails=deleted_emails,
                ):
                    continue
                filtered.append(ticket)
            return filtered

    async def get_override(self, ticket_id: str) -> dict[str, object] | None:
        session_factory = await self._ensure_session_factory()
        async with session_factory() as session:
            created = await session.get(Ticket, ticket_id)
            if created is not None:
                return self._record_from_model(created).as_ticket()
            override = await session.get(TicketOverride, ticket_id)
            if override is None:
                return None
            return self._override_from_model(override).as_dict()

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
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                now = utcnow()
                created = await session.get(Ticket, ticket_id)
                if created is not None:
                    created.subject = subject.strip()
                    created.customer = customer.strip()
                    created.customer_email = customer_email.strip()
                    created.status = status.strip()
                    created.priority = priority.strip()
                    created.team = team.strip()
                    created.assignment = assignment.strip()
                    created.queue = queue.strip()
                    created.category = category.strip()
                    created.summary = summary.strip()
                    created.metadata_updated_at_dt = now
                    created.last_reply_dt = now
                    await session.commit()
                    await session.refresh(created)
                    return self._record_from_model(created).as_ticket()

                override = await session.get(TicketOverride, ticket_id)
                if override is None:
                    override = TicketOverride(
                        ticket_id=ticket_id,
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
                        metadata_updated_at_dt=now,
                    )
                    session.add(override)
                else:
                    override.subject = subject.strip()
                    override.customer = customer.strip()
                    override.customer_email = customer_email.strip()
                    override.status = status.strip()
                    override.priority = priority.strip()
                    override.team = team.strip()
                    override.assignment = assignment.strip()
                    override.queue = queue.strip()
                    override.category = category.strip()
                    override.summary = summary.strip()
                    override.metadata_updated_at_dt = now
                await session.commit()
                await session.refresh(override)
                return self._override_from_model(override).as_dict()

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
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                ticket_id = await self._next_ticket_id(session, existing_ids)
                now = utcnow()
                due_at = now + timedelta(days=2)
                record = Ticket(
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
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return self._record_from_model(record).as_ticket()

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
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                reply = TicketReply(
                    ticket_id=ticket_id,
                    actor=actor.strip(),
                    direction="outbound",
                    channel=channel.strip(),
                    summary=summary.strip(),
                    body=escape(message),
                )
                session.add(reply)
                await session.flush()
                await session.execute(
                    update(Ticket)
                    .where(Ticket.id == ticket_id)
                    .values(
                        last_reply_dt=reply.timestamp_dt,
                        metadata_updated_at_dt=reply.timestamp_dt,
                    )
                )
                await session.commit()
                await session.refresh(reply)
                return self._reply_to_dict(reply)

    async def list_replies(self, ticket_id: str) -> list[dict[str, object]]:
        session_factory = await self._ensure_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(TicketReply)
                .where(TicketReply.ticket_id == ticket_id)
                .order_by(TicketReply.timestamp_dt)
            )
            replies = result.scalars().all()
            return [self._reply_to_dict(reply) for reply in replies]

    async def reset(self) -> None:
        """Clear stored tickets and overrides (useful for tests)."""

        async with self._lock:
            session_factory = self._session_factory
            if session_factory is None:
                self._ticket_sequence = self._sequence_floor
                self._external_sources.clear()
                return

            async with session_factory() as session:
                try:
                    await session.execute(delete(TicketReply))
                    await session.execute(delete(TicketOverride))
                    await session.execute(delete(Ticket))
                    await session.execute(delete(TicketDeletion))
                    await session.execute(delete(TicketSummary))
                    await session.commit()
            self._ticket_sequence = self._sequence_floor
            self._external_sources.clear()
            self._session_factory = None

    async def sync_external_records(
        self, source: str, records: Iterable[StoredTicketRecord]
    ) -> None:
        """Replace the external ticket catalogue for a given source."""

        normalized_source = source.strip().lower() or "external"
        async with self._lock:
            bucket: Dict[str, StoredTicketRecord] = {}
            for record in records:
                bucket[record.id] = record
            self._external_sources[normalized_source] = bucket

    async def _record_deletions(
        self, session: AsyncSession, values: Sequence[tuple[str, str]]
    ) -> None:
        for kind, value in values:
            if not value:
                continue
            normalized = self._normalized(value)
            if not normalized:
                continue
            existing = await session.execute(
                select(TicketDeletion).where(
                    TicketDeletion.kind == kind, TicketDeletion.value == normalized
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(TicketDeletion(kind=kind, value=normalized))

    async def delete_tickets_for_organization(
        self,
        *,
        organization_name: str,
        contact_emails: Iterable[str] | None = None,
    ) -> None:
        """Remove tickets tied to the provided organization metadata."""

        normalized_name = self._normalized(organization_name)
        normalized_emails: Set[str] = set()
        for email in contact_emails or []:
            normalized = self._normalized(email)
            if normalized:
                normalized_emails.add(normalized)

        async with self._lock:
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                deletion_values: list[tuple[str, str]] = []
                if normalized_name:
                    deletion_values.append(("customer", normalized_name))
                for email in normalized_emails:
                    deletion_values.append(("email", email))

                await self._record_deletions(session, deletion_values)

                ids_to_delete: Set[str] = set()
                if normalized_name:
                    results = await session.execute(
                        select(Ticket.id).where(
                            func.lower(Ticket.customer) == normalized_name
                        )
                    )
                    ids_to_delete.update(row[0] for row in results.all())

                if normalized_emails:
                    results = await session.execute(
                        select(Ticket.id).where(
                            func.lower(Ticket.customer_email).in_(
                                list(normalized_emails)
                            )
                        )
                    )
                    ids_to_delete.update(row[0] for row in results.all())

                if ids_to_delete:
                    await session.execute(
                        delete(TicketReply).where(TicketReply.ticket_id.in_(ids_to_delete))
                    )
                    await session.execute(
                        delete(Ticket).where(Ticket.id.in_(ids_to_delete))
                    )

                if normalized_name:
                    await session.execute(
                        delete(TicketOverride).where(
                            func.lower(TicketOverride.customer) == normalized_name
                        )
                    )
                if normalized_emails:
                    await session.execute(
                        delete(TicketOverride).where(
                            func.lower(TicketOverride.customer_email).in_(
                                list(normalized_emails)
                            )
                        )
                    )

                await session.commit()

            deleted_customers = {normalized_name} if normalized_name else set()
            deleted_emails = set(normalized_emails)

            for source, records in list(self._external_sources.items()):
                filtered: Dict[str, StoredTicketRecord] = {}
                for ticket_id, record in records.items():
                    if self._is_deleted(
                        record.customer,
                        record.customer_email,
                        deleted_customers=deleted_customers,
                        deleted_emails=deleted_emails,
                    ):
                        continue
                    filtered[ticket_id] = record
                if filtered:
                    self._external_sources[source] = filtered
                else:
                    self._external_sources.pop(source, None)

    async def record_summary(
        self,
        ticket_id: str,
        *,
        provider: str,
        model: str | None = None,
        summary: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, object]:
        """Persist the latest generated summary for a ticket."""

        normalized_provider = provider.strip() or "ollama"

        async with self._lock:
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                record = await session.get(TicketSummary, ticket_id)
                if record is None:
                    record = TicketSummary(ticket_id=ticket_id)
                    session.add(record)
                record.provider = normalized_provider
                record.model = model.strip() if isinstance(model, str) and model.strip() else None
                if summary is not None and summary.strip():
                    record.summary = summary.strip()
                elif record.summary is None:
                    record.summary = None
                record.error_message = error_message.strip() if isinstance(error_message, str) and error_message.strip() else None
                record.updated_at_dt = utcnow()
                await session.commit()
                await session.refresh(record)
                return self._summary_from_model(record).as_dict()

    async def get_summary(self, ticket_id: str) -> dict[str, object] | None:
        session_factory = await self._ensure_session_factory()
        async with session_factory() as session:
            record = await session.get(TicketSummary, ticket_id)
            if record is None:
                return None
            return self._summary_from_model(record).as_dict()

    async def clear_summary(self, ticket_id: str) -> None:
        async with self._lock:
            session_factory = await self._ensure_session_factory()
            async with session_factory() as session:
                await session.execute(
                    delete(TicketSummary).where(TicketSummary.ticket_id == ticket_id)
                )
                await session.commit()


ticket_store = TicketStore()
