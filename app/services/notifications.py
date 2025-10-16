"""Notification delivery helpers for automation actions."""

from __future__ import annotations

import logging
import unicodedata
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import IntegrationModule

logger = logging.getLogger(__name__)


async def _load_ntfy_settings(session: AsyncSession) -> tuple[bool, dict[str, Any]]:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == "ntfy")
    )
    module = result.scalar_one_or_none()
    if module is None:
        return False, {}
    return bool(module.enabled), dict(module.settings or {})


def _sanitize_header_value(value: str | None) -> str | None:
    """Return an ASCII-safe header value or ``None`` when empty."""

    if value is None:
        return None

    sanitized = value.replace("\r", " ").replace("\n", " ")
    # Replace common Unicode dash characters with a standard hyphen.
    for dash in ("—", "–", "―", "−"):
        sanitized = sanitized.replace(dash, "-")

    normalized = unicodedata.normalize("NFKD", sanitized)
    ascii_bytes = normalized.encode("ascii", "ignore")
    ascii_value = ascii_bytes.decode("ascii")
    ascii_value = " ".join(ascii_value.split())
    return ascii_value or None


async def send_ntfy_notification(
    session: AsyncSession,
    *,
    message: str,
    automation_name: str,
    event_type: str,
    ticket_identifier: str,
) -> None:
    """Deliver an ntfy notification when the integration is enabled."""

    enabled, settings = await _load_ntfy_settings(session)
    app_settings = get_settings()

    base_url = settings.get("base_url") or app_settings.ntfy_base_url
    topic = settings.get("topic") or app_settings.ntfy_topic
    token = settings.get("token") or app_settings.ntfy_token

    if not enabled:
        logger.debug(
            "Skipping ntfy notification because the integration is disabled.",
        )
        return

    if not base_url or not topic:
        logger.warning(
            "ntfy integration is enabled but missing base URL or topic configuration."
        )
        return

    normalized_base = base_url.rstrip("/")
    normalized_topic = quote(str(topic).strip("/"), safe="/-_.~")
    endpoint = f"{normalized_base}/{normalized_topic}"

    headers: dict[str, str] = {"Content-Type": "text/plain; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    title = _sanitize_header_value(f"{automation_name} — {event_type}".strip())
    if title:
        headers["Title"] = title

    automation_header = _sanitize_header_value(automation_name)
    if automation_header:
        headers["X-TacticalDesk-Automation"] = automation_header

    ticket_header = _sanitize_header_value(ticket_identifier)
    if ticket_header:
        headers["X-TacticalDesk-Ticket"] = ticket_header

    timeout = httpx.Timeout(10.0, connect=5.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, content=message.encode("utf-8"), headers=headers)
        response.raise_for_status()
        logger.info(
            "Sent ntfy notification for automation '%s' to topic '%s'.",
            automation_name,
            topic,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "Failed to send ntfy notification for automation '%s': %s",
            automation_name,
            exc,
        )

