from __future__ import annotations

from datetime import timedelta

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_post_webhook import build_http_post_variable_context
from app.core.db import get_session
from app.models import WebhookDelivery, utcnow
from app.schemas import (
    HttpPostWebhookReceipt,
    WebhookDeliveryRead,
    WebhookStatus,
)
from app.services import dispatch_ticket_event

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

logger = logging.getLogger(__name__)


async def _get_webhook_by_event_id(
    event_id: str, session: AsyncSession
) -> WebhookDelivery:
    result = await session.execute(
        select(WebhookDelivery).where(WebhookDelivery.event_id == event_id)
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook delivery not found",
        )
    return webhook


@router.post(
    "/https-post",
    response_model=HttpPostWebhookReceipt,
    name="receive_https_post_webhook",
)
async def receive_https_post_webhook(
    payload: dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_session),
) -> HttpPostWebhookReceipt:
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    logger.info(
        "Received HTTPS POST webhook payload",
        extra={"payload_preview": payload_json[:4096]},
    )

    try:
        variables = build_http_post_variable_context(payload)
    except TypeError as exc:
        logger.error(
            "HTTPS POST webhook payload rejected: %s",
            exc,
            extra={"payload_preview": payload_json[:4096]},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object",
        ) from exc

    mapped_keys = sorted(key for key, value in variables.items() if value)
    logger.info(
        "HTTPS POST webhook mapped keys",
        extra={"mapped_keys": mapped_keys},
    )

    await dispatch_ticket_event(
        session,
        event_type="HTTP POST Webhook Received",
        extra_variables=variables,
    )
    return HttpPostWebhookReceipt(variables=variables, mapped_keys=mapped_keys)


@router.get("/", response_model=list[WebhookDeliveryRead])
async def list_webhook_deliveries(
    session: AsyncSession = Depends(get_session),
) -> list[WebhookDeliveryRead]:
    result = await session.execute(
        select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc())
    )
    deliveries = result.scalars().all()
    return [WebhookDeliveryRead.from_orm(delivery) for delivery in deliveries]


@router.post("/{event_id}/pause", response_model=WebhookDeliveryRead)
async def pause_webhook_delivery(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> WebhookDeliveryRead:
    delivery = await _get_webhook_by_event_id(event_id, session)
    if delivery.status != WebhookStatus.PAUSED.value:
        delivery.status = WebhookStatus.PAUSED.value
        delivery.next_retry_at = None
        delivery.updated_at = utcnow()
        await session.commit()
        await session.refresh(delivery)
    return WebhookDeliveryRead.from_orm(delivery)


@router.post("/{event_id}/resume", response_model=WebhookDeliveryRead)
async def resume_webhook_delivery(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> WebhookDeliveryRead:
    delivery = await _get_webhook_by_event_id(event_id, session)
    now = utcnow()
    delivery.status = WebhookStatus.RETRYING.value
    delivery.next_retry_at = now + timedelta(minutes=5)
    delivery.updated_at = now
    await session.commit()
    await session.refresh(delivery)
    return WebhookDeliveryRead.from_orm(delivery)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_webhook_delivery(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> Response:
    delivery = await _get_webhook_by_event_id(event_id, session)
    await session.delete(delivery)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
