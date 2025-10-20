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
from app.services.webhook_logging import log_module_api_call

logger = logging.getLogger(__name__)


async def _load_ntfy_settings(
    session: AsyncSession,
) -> tuple[IntegrationModule | None, bool, dict[str, Any]]:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == "ntfy")
    )
    module = result.scalar_one_or_none()
    if module is None:
        return None, False, {}
    return module, bool(module.enabled), dict(module.settings or {})


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
    topic_override: str | None = None,
) -> None:
    """Deliver an ntfy notification when the integration is enabled.

    The ``topic_override`` parameter allows automation actions to specify a
    custom destination topic. When provided, this value takes precedence over
    the integration module configuration and application defaults.
    """

    module, enabled, settings = await _load_ntfy_settings(session)
    app_settings = get_settings()

    def _clean(value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        cleaned = str(value).strip()
        return cleaned or None

    base_url = _clean(settings.get("base_url")) or _clean(
        app_settings.ntfy_base_url
    )
    configured_topic = _clean(settings.get("topic")) or _clean(
        app_settings.ntfy_topic
    )
    token = _clean(settings.get("token")) or _clean(app_settings.ntfy_token)
    topic = _clean(topic_override) or configured_topic

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

    masked_headers = {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"authorization", "x-ntfy-token"}
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint, content=message.encode("utf-8"), headers=headers
            )
        response.raise_for_status()
        logger.info(
            "Sent ntfy notification for automation '%s' to topic '%s'.",
            automation_name,
            topic,
        )
        if module is not None:
            status_code = getattr(response, "status_code", None)
            body_text = getattr(response, "text", None)
            await log_module_api_call(
                session,
                module=module,
                request_method="POST",
                request_url=endpoint,
                request_payload={
                    "headers": masked_headers,
                    "topic": normalized_topic,
                    "message_preview": message[:200],
                },
                response_status_code=status_code,
                response_payload=body_text,
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "Failed to send ntfy notification for automation '%s': %s",
            automation_name,
            exc,
        )
        if module is not None:
            await log_module_api_call(
                session,
                module=module,
                request_method="POST",
                request_url=endpoint,
                request_payload={
                    "headers": masked_headers,
                    "topic": normalized_topic,
                    "message_preview": message[:200],
                },
                error_message=str(exc),
            )

