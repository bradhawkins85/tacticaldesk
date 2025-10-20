"""Helpers for generating and persisting ticket summaries."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tickets import ticket_store
from app.services.ollama import request_ticket_summary

RESOLUTION_RESOLVED = "resolved"
RESOLUTION_IN_PROGRESS = "in_progress"
_RESOLVED_KEYWORDS = {
    "resolved",
    "fixed",
    "completed",
    "closed",
    "restored",
    "solved",
    "implemented",
}


def _normalize(value: Any | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_timestamp(entry: dict[str, Any]) -> datetime | None:
    raw_dt = entry.get("timestamp_dt")
    if isinstance(raw_dt, datetime):
        if raw_dt.tzinfo is None:
            raw_dt = raw_dt.replace(tzinfo=timezone.utc)
        return raw_dt
    iso_value = _normalize(entry.get("timestamp_iso"))
    if iso_value:
        try:
            candidate = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        return candidate
    return None


def _build_combined_history(
    ticket_history: Iterable[dict[str, Any]],
    reply_history: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    for entry in ticket_history:
        entry_dict = dict(entry)
        combined.append(entry_dict)
    for reply in reply_history:
        entry_dict = dict(reply)
        entry_dict.setdefault("actor", "Service Desk")
        entry_dict.setdefault("channel", _normalize(reply.get("channel")) or "Portal")
        entry_dict.setdefault("body", reply.get("body") or reply.get("message") or "")
        timestamp = _parse_timestamp(entry_dict)
        if timestamp is not None:
            entry_dict["timestamp_dt"] = timestamp
            entry_dict.setdefault("timestamp_iso", timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
        combined.append(entry_dict)

    combined.sort(
        key=lambda entry: _parse_timestamp(entry) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return combined


def _fallback_summary(ticket: dict[str, Any], history: list[dict[str, Any]]) -> str:
    subject = _normalize(ticket.get("subject")) or "Service desk ticket"
    customer = _normalize(ticket.get("customer"))
    status = _normalize(ticket.get("status")) or "Open"
    priority = _normalize(ticket.get("priority"))
    assignment = _normalize(ticket.get("assignment"))
    queue = _normalize(ticket.get("queue"))

    details = [subject]
    if customer:
        details.append(f"for {customer}")
    if status:
        details.append(f"is currently {status.lower()}")
    if priority:
        details.append(f"at {priority.lower()} priority")
    if assignment:
        details.append(f"with {assignment}")
    if queue:
        details.append(f"in the {queue} queue")

    headline = " ".join(details).strip()

    latest_update = ""
    for entry in reversed(history):
        candidate = _normalize(entry.get("summary")) or _normalize(entry.get("body"))
        if candidate:
            latest_update = candidate
            break
    if not latest_update:
        latest_update = _normalize(ticket.get("summary"))

    if latest_update:
        narrative = f"Latest update: {latest_update}"
    else:
        narrative = "Latest update: awaiting details."

    combined = f"{headline}. {narrative}".strip()
    return combined or "Ticket summary unavailable."


def _normalize_resolution_state(value: Any | None) -> str:
    raw = _normalize(value).lower()
    if not raw:
        return ""
    if raw in {RESOLUTION_RESOLVED, "resolved", "complete", "completed", "done", "closed", "fixed"}:
        return RESOLUTION_RESOLVED
    if raw in {RESOLUTION_IN_PROGRESS, "in_progress", "in-progress", "pending", "open"}:
        return RESOLUTION_IN_PROGRESS
    return ""


def _infer_resolution_state(
    ticket: dict[str, Any],
    summary: str,
    hint: Any | None = None,
) -> str:
    normalized = _normalize_resolution_state(hint)
    if normalized:
        return normalized

    status = _normalize(ticket.get("status")).lower()
    if status:
        if any(keyword in status for keyword in ("resolved", "closed", "completed", "done", "solved")):
            return RESOLUTION_RESOLVED

    lowered_summary = summary.lower()
    for keyword in _RESOLVED_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered_summary):
            return RESOLUTION_RESOLVED

    return RESOLUTION_IN_PROGRESS


async def refresh_ticket_summary(
    session: AsyncSession,
    ticket: dict[str, Any],
) -> dict[str, Any] | None:
    """Refresh the persisted summary for the provided ticket."""

    ticket_id = _normalize(ticket.get("id")) or _normalize(ticket.get("ticket_id"))
    if not ticket_id:
        return None

    stored_replies = await ticket_store.list_replies(ticket_id)
    ticket_history = ticket.get("history") or []
    history = _build_combined_history(ticket_history, stored_replies)

    ollama_result = await request_ticket_summary(session, ticket, history)

    summary_text = _normalize(ollama_result.get("summary"))
    provider = _normalize(ollama_result.get("provider")) or "ollama"
    model = _normalize(ollama_result.get("model")) or None
    error_message = _normalize(ollama_result.get("error")) or None
    resolution_state = _normalize_resolution_state(ollama_result.get("resolution_state"))

    if not summary_text:
        summary_text = _fallback_summary(ticket, history)
        provider = "fallback"

    if not summary_text:
        summary_text = "Ticket summary unavailable."

    if not resolution_state:
        resolution_state = _infer_resolution_state(ticket, summary_text)

    record = await ticket_store.record_summary(
        ticket_id,
        provider=provider,
        model=model,
        summary=summary_text,
        error_message=error_message,
        resolution_state=resolution_state,
    )
    record["used_fallback"] = provider == "fallback"
    record["resolution_state"] = resolution_state
    return record
