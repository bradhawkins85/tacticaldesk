"""Integration helpers for interacting with a local Ollama deployment."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationModule

LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3"
REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


async def get_ollama_module(session: AsyncSession) -> tuple[IntegrationModule | None, dict[str, Any]]:
    """Fetch the Ollama integration module and normalised settings."""

    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == "ollama")
    )
    module = result.scalar_one_or_none()
    settings: dict[str, Any] = {}
    if module and isinstance(module.settings, dict):
        settings = dict(module.settings)
    return module, settings


def _sanitize_base_url(raw: str | None) -> str:
    base = (raw or "").strip() or DEFAULT_BASE_URL
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"}:
        return DEFAULT_BASE_URL
    if not parsed.netloc:
        return DEFAULT_BASE_URL
    return base.rstrip("/")


def _normalise_text(value: Any | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _strip_html(value: str) -> str:
    """Remove basic HTML tags to avoid confusing the language model."""

    if not value:
        return ""
    return re.sub(r"<[^>]+>", " ", value)


def build_ticket_prompt(
    ticket: dict[str, Any],
    history: Iterable[dict[str, Any]],
    *,
    instructions: str | None = None,
) -> str:
    """Construct a deterministic prompt describing the ticket context."""

    subject = _normalise_text(ticket.get("subject"))
    customer = _normalise_text(ticket.get("customer"))
    status = _normalise_text(ticket.get("status"))
    priority = _normalise_text(ticket.get("priority"))
    assignment = _normalise_text(ticket.get("assignment"))
    queue = _normalise_text(ticket.get("queue"))
    category = _normalise_text(ticket.get("category"))
    summary = _normalise_text(ticket.get("summary"))

    lines = [
        "You are an operations assistant that summarises service desk tickets for analysts.",
        "Summaries must be concise (<= 80 words) and highlight the problem, current status, and next step.",
        "Avoid personally identifiable information or credentials.",
        "Respond with a single paragraph.",
        "",  # blank line
        "Ticket metadata:",
        f"- Subject: {subject or 'N/A'}",
        f"- Customer: {customer or 'N/A'}",
        f"- Status: {status or 'N/A'}",
        f"- Priority: {priority or 'N/A'}",
        f"- Assignment: {assignment or 'N/A'}",
        f"- Queue: {queue or 'N/A'}",
        f"- Category: {category or 'N/A'}",
    ]

    if summary:
        lines.extend(["- Description:", summary])

    cleaned_history: list[str] = []
    for index, entry in enumerate(history):
        actor = _normalise_text(entry.get("actor")) or "Unknown actor"
        channel = _normalise_text(entry.get("channel")) or "Channel"
        body = _strip_html(_normalise_text(entry.get("body")))
        snippet = body or _normalise_text(entry.get("summary"))
        timestamp = _normalise_text(entry.get("timestamp_iso")) or _normalise_text(
            entry.get("timestamp_dt")
        )
        cleaned_history.append(
            f"{index + 1}. [{timestamp}] {actor} via {channel}: {snippet or 'No details provided.'}"
        )
        if len(cleaned_history) >= 5:
            break

    if cleaned_history:
        lines.append("")
        lines.append("Recent updates:")
        lines.extend(cleaned_history)

    if instructions:
        instructions_text = instructions.strip()
        if instructions_text:
            lines.extend(["", "Additional operator instructions:", instructions_text])

    lines.extend(["", "Return only the final summary paragraph without prefixes or commentary."])
    return "\n".join(lines)


async def request_ticket_summary(
    session: AsyncSession,
    ticket: dict[str, Any],
    history: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Call Ollama to generate a natural-language summary for the ticket."""

    module, settings = await get_ollama_module(session)
    if module is None:
        return {
            "provider": "ollama",
            "summary": None,
            "model": None,
            "error": "Ollama module is not provisioned.",
            "enabled": False,
        }

    if not module.enabled:
        return {
            "provider": "ollama",
            "summary": None,
            "model": None,
            "error": "Ollama module is disabled.",
            "enabled": False,
        }

    base_url = _sanitize_base_url(settings.get("base_url") if isinstance(settings, dict) else None)
    model = _normalise_text(settings.get("model")) if isinstance(settings, dict) else ""
    prompt_override = (
        _normalise_text(settings.get("prompt")) if isinstance(settings, dict) else ""
    )

    target_model = model or DEFAULT_MODEL
    prompt = build_ticket_prompt(ticket, history, instructions=prompt_override)
    endpoint = urljoin(f"{base_url}/", "api/generate")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                endpoint,
                json={"model": target_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # pragma: no cover - defensive network guard
        LOGGER.warning("Ollama summary request failed: %s", exc)
        return {
            "provider": "ollama",
            "summary": None,
            "model": target_model,
            "error": str(exc),
            "enabled": True,
        }

    summary_text = ""
    if isinstance(payload, dict):
        if isinstance(payload.get("response"), str):
            summary_text = payload["response"].strip()
        elif isinstance(payload.get("message"), dict):
            message = payload["message"]
            content = message.get("content")
            if isinstance(content, str):
                summary_text = content.strip()
    if not summary_text:
        summary_text = _normalise_text(payload.get("data")) if isinstance(payload, dict) else ""

    if not summary_text:
        return {
            "provider": "ollama",
            "summary": None,
            "model": target_model,
            "error": "Ollama returned an empty response.",
            "enabled": True,
        }

    return {
        "provider": "ollama",
        "summary": summary_text,
        "model": target_model,
        "error": None,
        "enabled": True,
    }
