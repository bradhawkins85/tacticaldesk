from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Automation, utcnow
from app.schemas import AutomationRead, AutomationUpdate

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


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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

    if "cadence" in data:
        cleaned_cadence = _clean_optional_text(data["cadence"])
        if cleaned_cadence != automation.cadence:
            automation.cadence = cleaned_cadence
            updated = True

    if "trigger" in data:
        cleaned_trigger = _clean_optional_text(data["trigger"])
        if cleaned_trigger != automation.trigger:
            automation.trigger = cleaned_trigger
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
