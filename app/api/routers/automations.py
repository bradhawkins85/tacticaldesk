from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automations import EVENT_TRIGGER_SET
from app.core.db import get_session
from app.models import Automation, utcnow
from app.schemas import AutomationRead, AutomationTriggerFilter, AutomationUpdate

router = APIRouter(prefix="/api/automations", tags=["Automations"])


def _normalize_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    cleaned = kind.strip().lower()
    if cleaned == "":
        return None
    if cleaned not in {"scheduled", "event"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported automation kind",
        )
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _ensure_required_text(value: str | None, field: str) -> str:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} cannot be empty",
        )
    return cleaned


CRON_PART_PATTERN = re.compile(r"^[\w*/,-]+$", re.IGNORECASE)


def _normalize_cron_expression(
    value: str | None, *, allow_empty: bool = True
) -> str | None:
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        if allow_empty:
            return None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cron expression cannot be empty",
        )

    parts = cleaned.split()
    if len(parts) not in {5, 6}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cron expression must include 5 or 6 segments",
        )

    for part in parts:
        if not CRON_PART_PATTERN.match(part):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cron expression contains invalid characters",
            )

    return cleaned


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_trigger_filters(
    value: AutomationTriggerFilter | dict | None,
    *,
    automation_kind: str,
) -> AutomationTriggerFilter | None:
    if value is None:
        return None

    if automation_kind not in {"event", "scheduled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trigger filters are not supported for this automation type",
        )

    if isinstance(value, AutomationTriggerFilter):
        filters = value
    else:
        try:
            filters = AutomationTriggerFilter.parse_obj(value)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid trigger filter payload",
            ) from exc

    invalid_conditions = [
        condition.type
        for condition in filters.conditions
        if condition.type not in EVENT_TRIGGER_SET
    ]
    if invalid_conditions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported automation trigger in filters",
        )
    return filters


async def _get_automation(session: AsyncSession, automation_id: int) -> Automation:
    result = await session.execute(
        select(Automation).where(Automation.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    if automation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )
    return automation


@router.get("/", response_model=list[AutomationRead])
async def list_automations(
    *,
    kind: str | None = Query(default=None, description="Filter by automation kind"),
    session: AsyncSession = Depends(get_session),
) -> list[AutomationRead]:
    normalized_kind = _normalize_kind(kind)
    query = select(Automation)
    if normalized_kind:
        query = query.where(Automation.kind == normalized_kind)
    query = query.order_by(Automation.name.asc())
    result = await session.execute(query)
    automations: Iterable[Automation] = result.scalars().all()
    return [AutomationRead.from_orm(auto) for auto in automations]


@router.patch("/{automation_id}", response_model=AutomationRead)
async def update_automation(
    *,
    automation_id: int,
    payload: AutomationUpdate,
    session: AsyncSession = Depends(get_session),
) -> AutomationRead:
    automation = await _get_automation(session, automation_id)
    data = payload.dict(exclude_unset=True)
    if not data:
        return AutomationRead.from_orm(automation)

    updated = False

    if "name" in data and data["name"] is not None:
        cleaned = _ensure_required_text(data["name"], "Name")
        if cleaned != automation.name:
            automation.name = cleaned
            updated = True

    if "description" in data:
        cleaned_description = _clean_optional_text(data["description"])
        if cleaned_description != automation.description:
            automation.description = cleaned_description
            updated = True

    if "playbook" in data and data["playbook"] is not None:
        cleaned_playbook = _ensure_required_text(data["playbook"], "Playbook")
        if cleaned_playbook != automation.playbook:
            automation.playbook = cleaned_playbook
            updated = True

    if "cron_expression" in data:
        cleaned_cron = _normalize_cron_expression(
            data["cron_expression"],
            allow_empty=automation.kind != "scheduled",
        )
        if automation.kind == "scheduled" and cleaned_cron is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cron expression is required for scheduled automations",
            )
        if cleaned_cron != automation.cron_expression:
            automation.cron_expression = cleaned_cron
            updated = True

    if "trigger" in data:
        cleaned_trigger = _clean_optional_text(data["trigger"])
        if (
            automation.kind == "event"
            and cleaned_trigger is not None
            and cleaned_trigger not in EVENT_TRIGGER_SET
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported automation trigger",
            )
        if cleaned_trigger != automation.trigger:
            automation.trigger = cleaned_trigger
            updated = True

    if "trigger_filters" in data:
        raw_filters = data["trigger_filters"]
        filters = _normalize_trigger_filters(raw_filters, automation_kind=automation.kind)
        current_filters: AutomationTriggerFilter | None = None
        if automation.trigger_filters:
            try:
                current_filters = AutomationTriggerFilter.parse_obj(automation.trigger_filters)
            except ValidationError:
                current_filters = None

        if filters is None:
            if automation.trigger_filters is not None:
                automation.trigger_filters = None
                updated = True
        else:
            if current_filters != filters:
                automation.trigger_filters = filters.dict()
                updated = True

            if automation.kind == "event":
                if len(filters.conditions) == 1:
                    single_condition = filters.conditions[0]
                    single_label = single_condition.display_text()
                    if single_label != automation.trigger:
                        automation.trigger = single_label
                        updated = True
                else:
                    if automation.trigger is not None:
                        automation.trigger = None
                        updated = True

    if "status" in data:
        cleaned_status = _clean_optional_text(data["status"])
        if cleaned_status != automation.status:
            automation.status = cleaned_status
            updated = True

    if "next_run_at" in data:
        normalized_next = _normalize_datetime(data["next_run_at"])
        if normalized_next != automation.next_run_at:
            automation.next_run_at = normalized_next
            updated = True

    if "last_run_at" in data:
        normalized_last = _normalize_datetime(data["last_run_at"])
        if normalized_last != automation.last_run_at:
            automation.last_run_at = normalized_last
            updated = True

    if "last_trigger_at" in data:
        normalized_trigger = _normalize_datetime(data["last_trigger_at"])
        if normalized_trigger != automation.last_trigger_at:
            automation.last_trigger_at = normalized_trigger
            updated = True

    if updated:
        automation.updated_at = utcnow()
        session.add(automation)
        await session.commit()
        await session.refresh(automation)

    return AutomationRead.from_orm(automation)


@router.post("/{automation_id}/run")
async def run_automation(
    *,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    automation = await _get_automation(session, automation_id)
    if automation.kind != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only scheduled automations support manual execution",
        )

    automation.last_run_at = utcnow()
    automation.updated_at = utcnow()

    await session.commit()
    await session.refresh(automation)

    return {
        "detail": f"Queued manual execution for {automation.name}.",
        "last_run_at": automation.last_run_at.isoformat(),
    }


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    *,
    automation_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    automation = await _get_automation(session, automation_id)

    await session.delete(automation)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
