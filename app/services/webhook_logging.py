from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationModule, WebhookDelivery, utcnow
from app.schemas import WebhookStatus

_MAX_BODY_LENGTH = 4000


def _truncate_value(value: str) -> str:
    if len(value) <= _MAX_BODY_LENGTH:
        return value
    return value[: _MAX_BODY_LENGTH - 3] + "..."


def _normalize_payload(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, (dict, list, int, float, bool)):
        return payload
    text = str(payload)
    return {"text": _truncate_value(text)}


def _normalize_mapping(mapping: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if mapping is None:
        return None
    normalized: dict[str, Any] = {}
    for key, value in mapping.items():
        normalized[str(key)] = _normalize_payload(value)
    return normalized or None


def _generate_event_id(module: IntegrationModule) -> str:
    token = uuid4().hex[:12]
    return f"{module.slug}-{token}"


async def log_module_api_call(
    session: AsyncSession,
    *,
    module: IntegrationModule,
    request_method: str,
    request_url: str,
    request_payload: Mapping[str, Any] | None = None,
    response_status_code: int | None = None,
    response_payload: Any | None = None,
    error_message: str | None = None,
) -> WebhookDelivery:
    """Persist an outbound module API call to the webhook delivery log."""

    normalized_request = _normalize_mapping(request_payload)
    normalized_response = _normalize_payload(response_payload)

    status = WebhookStatus.DELIVERED.value
    if error_message or (response_status_code is not None and response_status_code >= 400):
        status = WebhookStatus.FAILED.value

    delivery = WebhookDelivery(
        event_id=_generate_event_id(module),
        endpoint=request_url,
        module_id=module.id,
        module_slug=module.slug,
        request_method=request_method.upper(),
        request_url=request_url,
        request_payload=normalized_request,
        status=status,
        response_status_code=response_status_code,
        response_payload=normalized_response,
        error_message=error_message,
        last_attempt_at=utcnow(),
        next_retry_at=None,
    )
    session.add(delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery
