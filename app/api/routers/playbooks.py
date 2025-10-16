from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Automation, Playbook, utcnow
from app.schemas import PlaybookCreate, PlaybookRead, PlaybookUpdate

router = APIRouter(prefix="/api/playbooks", tags=["Playbooks"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_slug(value: str) -> str:
    slug = value.strip().lower()
    return slug


async def _get_playbook(playbook_id: int, session: AsyncSession) -> Playbook:
    result = await session.execute(
        select(Playbook).where(Playbook.id == playbook_id)
    )
    playbook = result.scalar_one_or_none()
    if playbook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    return playbook


async def _serialize_playbook(
    playbook: Playbook,
    session: AsyncSession,
    automation_count: int | None = None,
) -> PlaybookRead:
    if automation_count is None:
        count_result = await session.execute(
            select(func.count()).select_from(Automation).where(
                Automation.playbook == playbook.name
            )
        )
        automation_count = int(count_result.scalar_one() or 0)
    return PlaybookRead(
        id=playbook.id,
        name=playbook.name,
        slug=playbook.slug,
        description=playbook.description,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        automation_count=automation_count,
    )


@router.get("/", response_model=list[PlaybookRead])
async def list_playbooks(session: AsyncSession = Depends(get_session)) -> list[PlaybookRead]:
    result = await session.execute(
        select(Playbook, func.count(Automation.id))
        .outerjoin(Automation, Automation.playbook == Playbook.name)
        .group_by(Playbook.id)
        .order_by(Playbook.name.asc())
    )
    rows = result.all()
    serialized: list[PlaybookRead] = []
    for playbook, automation_count in rows:
        serialized.append(
            PlaybookRead(
                id=playbook.id,
                name=playbook.name,
                slug=playbook.slug,
                description=playbook.description,
                created_at=playbook.created_at,
                updated_at=playbook.updated_at,
                automation_count=int(automation_count or 0),
            )
        )
    return serialized


@router.post("/", response_model=PlaybookRead, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    payload: PlaybookCreate,
    session: AsyncSession = Depends(get_session),
) -> PlaybookRead:
    name = payload.name.strip()
    slug = _normalize_slug(payload.slug)
    description = _clean_optional(payload.description)

    existing = await session.execute(select(Playbook).where(Playbook.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A playbook with this slug already exists",
        )

    existing_name = await session.execute(
        select(Playbook).where(Playbook.name == name)
    )
    if existing_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A playbook with this name already exists",
        )

    playbook = Playbook(name=name, slug=slug, description=description)
    session.add(playbook)
    await session.commit()
    await session.refresh(playbook)
    return await _serialize_playbook(playbook, session, automation_count=0)


@router.get("/{playbook_id}", response_model=PlaybookRead)
async def get_playbook(
    playbook_id: int, session: AsyncSession = Depends(get_session)
) -> PlaybookRead:
    playbook = await _get_playbook(playbook_id, session)
    return await _serialize_playbook(playbook, session)


@router.patch("/{playbook_id}", response_model=PlaybookRead)
async def update_playbook(
    playbook_id: int,
    payload: PlaybookUpdate,
    session: AsyncSession = Depends(get_session),
) -> PlaybookRead:
    playbook = await _get_playbook(playbook_id, session)
    data = payload.dict(exclude_unset=True)
    updated = False
    old_name = playbook.name
    name_changed = False

    if "name" in data and data["name"] is not None:
        cleaned_name = data["name"].strip()
        if cleaned_name and cleaned_name != playbook.name:
            conflict = await session.execute(
                select(Playbook).where(Playbook.name == cleaned_name)
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A playbook with this name already exists",
                )
            playbook.name = cleaned_name
            updated = True
            name_changed = True

    if "slug" in data and data["slug"] is not None:
        cleaned_slug = _normalize_slug(data["slug"])
        if cleaned_slug != playbook.slug:
            conflict = await session.execute(
                select(Playbook).where(Playbook.slug == cleaned_slug)
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A playbook with this slug already exists",
                )
            playbook.slug = cleaned_slug
            updated = True

    if "description" in data:
        cleaned_description = _clean_optional(data["description"])
        if cleaned_description != playbook.description:
            playbook.description = cleaned_description
            updated = True

    if name_changed:
        await session.execute(
            update(Automation)
            .where(Automation.playbook == old_name)
            .values(playbook=playbook.name)
        )
        updated = True

    if updated:
        playbook.updated_at = utcnow()
        session.add(playbook)
        await session.commit()
        await session.refresh(playbook)
    else:
        await session.refresh(playbook)

    return await _serialize_playbook(playbook, session)


@router.delete("/{playbook_id}", response_class=Response)
async def delete_playbook(
    playbook_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    playbook = await _get_playbook(playbook_id, session)
    count_result = await session.execute(
        select(func.count()).select_from(Automation).where(
            Automation.playbook == playbook.name
        )
    )
    automation_count = int(count_result.scalar_one() or 0)
    if automation_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a playbook that is linked to automations",
        )

    await session.delete(playbook)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
