"""Automation domain constants and helpers."""

from __future__ import annotations

EVENT_TRIGGER_OPTIONS: tuple[str, ...] = (
    "Ticket Created",
    "Ticket Updated by Technician",
    "Ticket Updated by Customer",
    "Ticket Status Changed",
    "Ticket Status Changed To",
    "Ticket Status Changed From",
    "Ticket Resolved",
)

EVENT_TRIGGER_SET: frozenset[str] = frozenset(EVENT_TRIGGER_OPTIONS)

VALUE_REQUIRED_TRIGGER_OPTIONS: frozenset[str] = frozenset(
    {
        "Ticket Status Changed To",
        "Ticket Status Changed From",
    }
)

TRIGGER_OPERATOR_OPTIONS: tuple[tuple[str, str], ...] = (
    ("equals", "Equals"),
    ("not_equals", "Does not equal"),
    ("contains", "Contains"),
)

TRIGGER_OPERATOR_LABELS: dict[str, str] = dict(TRIGGER_OPERATOR_OPTIONS)

