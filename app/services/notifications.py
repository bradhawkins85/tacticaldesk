"""Notification delivery helpers for automation actions."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import unicodedata
from email.message import EmailMessage
from typing import Any, Iterable
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


async def _load_smtp_settings(
    session: AsyncSession,
) -> tuple[IntegrationModule | None, bool, dict[str, Any]]:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == "smtp-email")
    )
    module = result.scalar_one_or_none()
    if module is None:
        return None, False, {}
    return module, bool(module.enabled), dict(module.settings or {})


def _clean_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_bool(value: object | None, default: bool | None = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _parse_port(value: object | None, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return default


def _parse_recipients(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        tokens = [token.strip() for token in value.replace(";", ",").split(",")]
        return [token for token in tokens if token]
    if isinstance(value, Iterable):
        results = []
        for item in value:
            cleaned = _clean_str(item)
            if cleaned:
                results.append(cleaned)
        return results
    cleaned = _clean_str(value)
    return [cleaned] if cleaned else []


async def send_smtp_email(
    session: AsyncSession,
    *,
    subject: str,
    body: str,
    automation_name: str,
    event_type: str,
    ticket_identifier: str,
    to: object | None = None,
    cc: object | None = None,
) -> None:
    """Deliver an email using the SMTP integration when enabled."""

    module, enabled, settings = await _load_smtp_settings(session)
    if not enabled:
        logger.debug("Skipping SMTP email because the integration is disabled.")
        return

    app_settings = get_settings()

    host = _clean_str(settings.get("smtp_host")) or _clean_str(app_settings.smtp_host)
    port = _parse_port(settings.get("smtp_port"), app_settings.smtp_port)
    username = _clean_str(settings.get("smtp_username")) or _clean_str(
        app_settings.smtp_username
    )
    password = _clean_str(settings.get("smtp_password")) or _clean_str(
        app_settings.smtp_password
    )
    sender = _clean_str(settings.get("smtp_sender")) or _clean_str(app_settings.smtp_sender)
    to_recipients = _parse_recipients(to)
    if not to_recipients:
        to_recipients = _parse_recipients(settings.get("smtp_recipients"))
    cc_recipients = _parse_recipients(cc)
    if not cc_recipients:
        cc_recipients = _parse_recipients(settings.get("smtp_cc"))
    bcc_recipients = _parse_recipients(settings.get("smtp_bcc"))

    if not host or not sender or not to_recipients:
        logger.warning(
            "SMTP integration is enabled but missing host, sender, or recipient configuration."
        )
        return

    use_ssl = _parse_bool(settings.get("smtp_use_ssl"), app_settings.smtp_use_ssl)
    use_tls = _parse_bool(settings.get("smtp_use_tls"), app_settings.smtp_use_tls)
    if use_ssl and use_tls:
        logger.warning(
            "SMTP integration has both TLS and SSL enabled; defaulting to implicit SSL only."
        )
        use_tls = False

    normalized_subject = _clean_str(subject) or f"Automation {automation_name} triggered"
    message = EmailMessage()
    message["Subject"] = normalized_subject
    message["From"] = sender
    message["To"] = ", ".join(to_recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    message["X-TacticalDesk-Automation"] = automation_name
    message["X-TacticalDesk-Event"] = event_type
    message["X-TacticalDesk-Ticket"] = ticket_identifier
    message.set_content(body)

    recipients = to_recipients + cc_recipients + bcc_recipients
    if not recipients:
        logger.warning("SMTP integration has no recipients after normalization; skipping send.")
        return

    endpoint = f"smtp://{host}:{port}"
    masked_payload = {
        "subject": normalized_subject,
        "to": to_recipients,
        "cc": cc_recipients,
        "bcc_count": len(bcc_recipients),
        "use_ssl": bool(use_ssl),
        "use_tls": bool(use_tls),
    }

    timeout = 15.0
    ssl_context = ssl.create_default_context()

    def _send_email_sync() -> dict[str, tuple[int, bytes]]:
        if use_ssl:
            smtp_client = smtplib.SMTP_SSL(
                host=host,
                port=port,
                timeout=timeout,
                context=ssl_context,
            )
        else:
            smtp_client = smtplib.SMTP(host=host, port=port, timeout=timeout)

        with smtp_client as client:
            client.ehlo()
            if use_tls and not use_ssl:
                client.starttls(context=ssl_context)
                client.ehlo()
            if username and password:
                client.login(username, password)
            errors = client.send_message(
                message,
                from_addr=sender,
                to_addrs=recipients,
            )
            return errors or {}

    try:
        send_errors = await asyncio.to_thread(_send_email_sync)
        if send_errors:
            response_code = 400
            response_payload: Any | None = {
                address: {"code": code, "message": response.decode("utf-8", "ignore")}
                for address, (code, response) in send_errors.items()
            }
        else:
            response_code = 250
            response_payload = "OK"

        logger.info(
            "Sent SMTP email for automation '%s' to %s (status: %s)",
            automation_name,
            ", ".join(to_recipients),
            response_code,
        )
        if module is not None:
            await log_module_api_call(
                session,
                module=module,
                request_method="SEND",
                request_url=endpoint,
                request_payload=masked_payload,
                response_status_code=response_code,
                response_payload=response_payload,
            )
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning(
            "Failed to send SMTP email for automation '%s': %s", automation_name, exc
        )
        if module is not None:
            await log_module_api_call(
                session,
                module=module,
                request_method="SEND",
                request_url=endpoint,
                request_payload=masked_payload,
                error_message=str(exc),
            )

