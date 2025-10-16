"""Service-layer helpers for domain-specific orchestration."""

from __future__ import annotations

__all__ = [
    "dispatch_ticket_event",
]

from .automation_events import dispatch_ticket_event
