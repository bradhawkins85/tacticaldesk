"""Automation domain constants and helpers."""

from __future__ import annotations

import re

_BASE_EVENT_TRIGGERS: tuple[str, ...] = (
    "Ticket Created",
    "Ticket Updated by Technician",
    "Ticket Updated by Customer",
    "Ticket Status Changed",
    "Ticket Status Changed To",
    "Ticket Status Changed From",
    "Ticket Resolved",
    "HTTP POST Webhook Received",
)

_CONDITION_TRIGGERS: tuple[str, ...] = (
    "Assigned SLA",
    "Assigned to",
    "Business Hours",
    "Contact Tags",
    "Customer",
    "Customer Tags",
    "Due date is passed",
    "Has SLA",
    "Has a contact",
    "Hours until due date",
    "Not updated in hours",
    "Part Order Received",
    "Ticket AI Classification",
    "Ticket Billing Status",
    "Ticket Issue Type",
    "Ticket Priority",
    "Ticket Status",
    "Ticket Subject",
    "Ticket Tags",
    "Ticket Type",
    "Ticket last comment subject",
)

EVENT_TRIGGER_OPTIONS: tuple[str, ...] = _BASE_EVENT_TRIGGERS + _CONDITION_TRIGGERS

EVENT_TRIGGER_SET: frozenset[str] = frozenset(EVENT_TRIGGER_OPTIONS)


def _slugify_action(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(tokens) or "action"


EVENT_AUTOMATION_ACTIONS: tuple[str, ...] = (
    "Add Private Comment",
    "Add Public Comment",
    "Add Subscriber",
    "Add Ticket Tag",
    "Assign to",
    "Attach Ticket Worksheet",
    "Change Issue Type",
    "Change Priority",
    "Change Status",
    "Send ntfy notification",
    "Email assignee",
    "Email custom email address",
    "Email customer/contact",
    "Fire \"Ticket Automation Triggered\" notification",
    "Post to Microsoft Teams",
    "Post to Slack",
    "Remove Ticket Tag",
    "Set SLA",
    "SMS Public Comment",
    "Send Manual SMS",
    "Update Ticket",
)

EVENT_AUTOMATION_ACTION_CHOICES: tuple[dict[str, str], ...] = tuple(
    {"name": action, "slug": _slugify_action(action)}
    for action in EVENT_AUTOMATION_ACTIONS
)

EVENT_AUTOMATION_ACTION_LOOKUP: dict[str, str] = {
    choice["slug"]: choice["name"] for choice in EVENT_AUTOMATION_ACTION_CHOICES
}

EVENT_AUTOMATION_ACTION_SLUGS: frozenset[str] = frozenset(
    EVENT_AUTOMATION_ACTION_LOOKUP
)

VALUE_REQUIRED_TRIGGER_OPTIONS: frozenset[str] = frozenset(
    {
        "Ticket Status Changed To",
        "Ticket Status Changed From",
        "Assigned SLA",
        "Assigned to",
        "Business Hours",
        "Contact Tags",
        "Customer",
        "Customer Tags",
        "Due date is passed",
        "Has SLA",
        "Has a contact",
        "Hours until due date",
        "Not updated in hours",
        "Part Order Received",
        "Ticket AI Classification",
        "Ticket Billing Status",
        "Ticket Issue Type",
        "Ticket Priority",
        "Ticket Status",
        "Ticket Subject",
        "Ticket Tags",
        "Ticket Type",
        "Ticket last comment subject",
    }
)

TRIGGER_OPERATOR_OPTIONS: tuple[tuple[str, str], ...] = (
    ("equals", "Equals"),
    ("not_equals", "Does not equal"),
    ("contains", "Contains"),
    ("matches_regex", "Matches regex"),
)

TRIGGER_OPERATOR_LABELS: dict[str, str] = dict(TRIGGER_OPERATOR_OPTIONS)

