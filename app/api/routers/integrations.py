from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import IntegrationModule, utcnow
from app.schemas import (
    IntegrationModuleCreate,
    IntegrationModuleRead,
    IntegrationModuleUpdate,
)

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


async def _get_integration_by_slug(slug: str, session: AsyncSession) -> IntegrationModule:
    result = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == slug)
    )
    module = result.scalar_one_or_none()
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration module not found",
        )
    return module


@router.get("/", response_model=list[IntegrationModuleRead])
async def list_integration_modules(
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationModuleRead]:
    result = await session.execute(
        select(IntegrationModule).order_by(IntegrationModule.name.asc())
    )
    modules = result.scalars().all()
    return [IntegrationModuleRead.from_orm(module) for module in modules]


@router.post(
    "/",
    response_model=IntegrationModuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration_module(
    payload: IntegrationModuleCreate,
    session: AsyncSession = Depends(get_session),
) -> IntegrationModuleRead:
    existing = await session.execute(
        select(IntegrationModule).where(IntegrationModule.slug == payload.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An integration module with this slug already exists",
        )

    settings_payload = payload.settings.dict(exclude_unset=True) if payload.settings else {}

    module = IntegrationModule(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        icon=payload.icon,
        enabled=payload.enabled,
        settings=settings_payload,
    )
    session.add(module)
    await session.commit()
    await session.refresh(module)
    return IntegrationModuleRead.from_orm(module)


@router.get("/{slug}", response_model=IntegrationModuleRead)
async def get_integration_module(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> IntegrationModuleRead:
    module = await _get_integration_by_slug(slug, session)
    return IntegrationModuleRead.from_orm(module)


@router.patch("/{slug}", response_model=IntegrationModuleRead)
async def update_integration_module(
    slug: str,
    payload: IntegrationModuleUpdate,
    session: AsyncSession = Depends(get_session),
) -> IntegrationModuleRead:
    module = await _get_integration_by_slug(slug, session)

    updated = False
    data = payload.dict(exclude_unset=True)

    if "name" in data and data["name"] and data["name"] != module.name:
        module.name = data["name"]
        updated = True
    if "description" in data and data["description"] != module.description:
        module.description = data["description"]
        updated = True
    if "icon" in data and data["icon"] != module.icon:
        module.icon = data["icon"]
        updated = True
    if "enabled" in data and data["enabled"] is not None and data["enabled"] != module.enabled:
        module.enabled = bool(data["enabled"])
        updated = True
    if "settings" in data and data["settings"] is not None:
        raw_settings = data["settings"]
        if isinstance(raw_settings, dict):
            settings_payload = raw_settings
        else:
            settings_payload = raw_settings.dict(exclude_unset=True)
        cleaned_settings = {k: v for k, v in settings_payload.items() if v is not None}
        if module.settings is None:
            module.settings = {}
        module.settings.update(cleaned_settings)
        # Remove keys explicitly set to null
        for key in [key for key, value in settings_payload.items() if value is None]:
            module.settings.pop(key, None)
        updated = True

    if updated:
        module.updated_at = utcnow()
        await session.commit()
        await session.refresh(module)

    return IntegrationModuleRead.from_orm(module)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_integration_module(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    module = await _get_integration_by_slug(slug, session)
    await session.delete(module)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
