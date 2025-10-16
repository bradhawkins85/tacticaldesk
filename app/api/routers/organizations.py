from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Organization, utcnow
from app.schemas import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)

router = APIRouter(prefix="/api/organizations", tags=["Organizations"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def _get_organization_by_id(
    organization_id: int, session: AsyncSession
) -> Organization:
    result = await session.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return organization


@router.get("/", response_model=list[OrganizationRead])
async def list_organizations(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[OrganizationRead]:
    query = select(Organization).order_by(Organization.name.asc())
    if not include_archived:
        query = query.where(Organization.is_archived.is_(False))
    result = await session.execute(query)
    organizations = result.scalars().all()
    return [OrganizationRead.from_orm(org) for org in organizations]


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    name = payload.name.strip()
    slug = payload.slug.strip().lower()
    description = _clean_optional(payload.description)
    contact_email = _clean_optional(payload.contact_email)

    existing = await session.execute(
        select(Organization).where(Organization.slug == slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this slug already exists",
        )

    organization = Organization(
        name=name,
        slug=slug,
        description=description,
        contact_email=contact_email,
        is_archived=False,
    )
    session.add(organization)
    await session.commit()
    await session.refresh(organization)
    return OrganizationRead.from_orm(organization)


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: int,
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    organization = await _get_organization_by_id(organization_id, session)
    return OrganizationRead.from_orm(organization)


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    organization_id: int,
    payload: OrganizationUpdate,
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    organization = await _get_organization_by_id(organization_id, session)

    data = payload.dict(exclude_unset=True)
    updated = False

    if "name" in data and data["name"] is not None:
        cleaned_name = data["name"].strip()
        if cleaned_name and cleaned_name != organization.name:
            organization.name = cleaned_name
            updated = True

    if "slug" in data and data["slug"] is not None:
        cleaned_slug = data["slug"].strip().lower()
        if cleaned_slug != organization.slug:
            existing = await session.execute(
                select(Organization).where(Organization.slug == cleaned_slug)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An organization with this slug already exists",
                )
            organization.slug = cleaned_slug
            updated = True

    if "description" in data:
        cleaned_description = _clean_optional(data["description"])
        if cleaned_description != organization.description:
            organization.description = cleaned_description
            updated = True

    if "contact_email" in data:
        cleaned_email = _clean_optional(data["contact_email"])
        if cleaned_email != organization.contact_email:
            organization.contact_email = cleaned_email
            updated = True

    if "is_archived" in data and data["is_archived"] is not None:
        desired_state = bool(data["is_archived"])
        if desired_state != organization.is_archived:
            organization.is_archived = desired_state
            updated = True

    if updated:
        organization.updated_at = utcnow()
        await session.commit()
        await session.refresh(organization)

    return OrganizationRead.from_orm(organization)
