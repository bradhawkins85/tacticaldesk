"""Automation domain constants and helpers."""

from __future__ import annotations

_BASE_EVENT_TRIGGERS: tuple[str, ...] = (
    "Ticket Created",
    "Ticket Updated by Technician",
    "Ticket Updated by Customer",
    "Ticket Status Changed",
    "Ticket Status Changed To",
    "Ticket Status Changed From",
    "Ticket Resolved",
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
)

TRIGGER_OPERATOR_LABELS: dict[str, str] = dict(TRIGGER_OPERATOR_OPTIONS)

