"""Template variable helpers for automation payloads and notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import re

_VARIABLE_PATTERN = re.compile(r"{{\s*([a-z0-9_.]+)\s*}}", re.IGNORECASE)


def _serialize_value(value: Any) -> str:
    """Convert supported values into a normalized string representation."""

    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def render_template_value(template: str, variables: Mapping[str, Any]) -> str:
    """Render a template string by replacing {{variable}} tokens with context."""

    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if not key:
            return ""
        value = variables.get(key)
        if value is None:
            return ""
        return _serialize_value(value)

    return _VARIABLE_PATTERN.sub(_replace, template)


_PREVIOUS_VALUE_FIELDS: tuple[str, ...] = (
    "status",
    "priority",
    "assignment",
    "team",
    "queue",
)


def build_ticket_variable_context(
    *,
    event_type: str,
    triggered_at: datetime,
    ticket_before: Mapping[str, Any] | None = None,
    ticket_after: Mapping[str, Any] | None = None,
    ticket_payload: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Build a mapping of template variables for the current ticket context."""

    context: dict[str, str] = {}
    ticket_before = ticket_before or {}
    ticket_after = ticket_after or {}
    ticket_payload = ticket_payload or {}

    keys: set[str] = set()
    for source in (ticket_before, ticket_after, ticket_payload):
        for key in source:
            if isinstance(key, str):
                keys.add(key)

    for key in sorted(keys):
        value = ticket_after.get(key)
        if value is None:
            value = ticket_payload.get(key)
        if value is None:
            value = ticket_before.get(key)
        context[f"ticket.{key}"] = _serialize_value(value)

    for field in _PREVIOUS_VALUE_FIELDS:
        if field in ticket_before:
            context[f"ticket.previous_{field}"] = _serialize_value(
                ticket_before.get(field)
            )

    context["event.type"] = _serialize_value(event_type)
    context["event.triggered_at"] = _serialize_value(triggered_at)

    return context


AUTOMATION_TEMPLATE_VARIABLES: tuple[dict[str, str], ...] = (
    {
        "key": "ticket.id",
        "label": "Ticket ID",
        "description": "Unique identifier for the ticket (for example TD-4821).",
    },
    {
        "key": "ticket.subject",
        "label": "Subject",
        "description": "Latest ticket subject provided by the requester or technician.",
    },
    {
        "key": "ticket.customer",
        "label": "Customer",
        "description": "Customer or organisation name associated with the ticket.",
    },
    {
        "key": "ticket.customer_email",
        "label": "Customer email",
        "description": "Primary contact email stored on the ticket record.",
    },
    {
        "key": "ticket.status",
        "label": "Status",
        "description": "Current workflow status after the most recent update.",
    },
    {
        "key": "ticket.previous_status",
        "label": "Previous status",
        "description": "Ticket status value prior to the triggering update.",
    },
    {
        "key": "ticket.priority",
        "label": "Priority",
        "description": "Current ticket priority label.",
    },
    {
        "key": "ticket.previous_priority",
        "label": "Previous priority",
        "description": "Ticket priority value before the automation executed.",
    },
    {
        "key": "ticket.team",
        "label": "Team",
        "description": "Assigned response team for the ticket after the update.",
    },
    {
        "key": "ticket.previous_team",
        "label": "Previous team",
        "description": "Team assignment prior to the triggering update.",
    },
    {
        "key": "ticket.assignment",
        "label": "Assignee",
        "description": "Technician currently assigned to the ticket.",
    },
    {
        "key": "ticket.previous_assignment",
        "label": "Previous assignee",
        "description": "Technician assignment before the automation fired.",
    },
    {
        "key": "ticket.queue",
        "label": "Queue",
        "description": "Queue or workflow lane associated with the ticket.",
    },
    {
        "key": "ticket.previous_queue",
        "label": "Previous queue",
        "description": "Queue value prior to the triggering change.",
    },
    {
        "key": "ticket.category",
        "label": "Category",
        "description": "Ticket category captured on the most recent update.",
    },
    {
        "key": "ticket.summary",
        "label": "Summary",
        "description": "Latest summary or troubleshooting notes captured on the ticket.",
    },
    {
        "key": "event.type",
        "label": "Event type",
        "description": "Normalized Tactical Desk event name that triggered the automation.",
    },
    {
        "key": "event.triggered_at",
        "label": "Triggered at (UTC)",
        "description": "ISO 8601 timestamp (UTC) when the automation executed.",
    },
)

