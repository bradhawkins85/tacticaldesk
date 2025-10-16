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
