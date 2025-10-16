from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Contact, Organization, utcnow
from app.schemas import (
    ContactCreate,
    ContactRead,
    ContactUpdate,
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


async def _get_contact_by_id(
    *,
    contact_id: int,
    organization_id: int,
    session: AsyncSession,
) -> Contact:
    result = await session.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == organization_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    return contact


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


@router.get("/{organization_id}/contacts", response_model=list[ContactRead])
async def list_contacts(
    organization_id: int, session: AsyncSession = Depends(get_session)
) -> list[ContactRead]:
    await _get_organization_by_id(organization_id, session)
    result = await session.execute(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .order_by(Contact.name.asc())
    )
    contacts = result.scalars().all()
    return [ContactRead.from_orm(contact) for contact in contacts]


@router.post(
    "/{organization_id}/contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact(
    organization_id: int,
    payload: ContactCreate,
    session: AsyncSession = Depends(get_session),
) -> ContactRead:
    organization = await _get_organization_by_id(organization_id, session)

    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name cannot be empty",
        )

    job_title = _clean_optional(payload.job_title)
    email = _clean_optional(payload.email)
    phone = _clean_optional(payload.phone)
    notes = _clean_optional(payload.notes)

    contact = Contact(
        organization_id=organization.id,
        name=name,
        job_title=job_title,
        email=email,
        phone=phone,
        notes=notes,
    )
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return ContactRead.from_orm(contact)


@router.patch(
    "/{organization_id}/contacts/{contact_id}", response_model=ContactRead
)
async def update_contact(
    organization_id: int,
    contact_id: int,
    payload: ContactUpdate,
    session: AsyncSession = Depends(get_session),
) -> ContactRead:
    await _get_organization_by_id(organization_id, session)
    contact = await _get_contact_by_id(
        contact_id=contact_id, organization_id=organization_id, session=session
    )

    data = payload.dict(exclude_unset=True)
    updated = False

    if "name" in data and data["name"] is not None:
        cleaned_name = data["name"].strip()
        if not cleaned_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name cannot be empty",
            )
        if cleaned_name != contact.name:
            contact.name = cleaned_name
            updated = True

    if "job_title" in data:
        cleaned_job_title = _clean_optional(data["job_title"])
        if cleaned_job_title != contact.job_title:
            contact.job_title = cleaned_job_title
            updated = True

    if "email" in data:
        cleaned_email = _clean_optional(data["email"])
        if cleaned_email != contact.email:
            contact.email = cleaned_email
            updated = True

    if "phone" in data:
        cleaned_phone = _clean_optional(data["phone"])
        if cleaned_phone != contact.phone:
            contact.phone = cleaned_phone
            updated = True

    if "notes" in data:
        cleaned_notes = _clean_optional(data["notes"])
        if cleaned_notes != contact.notes:
            contact.notes = cleaned_notes
            updated = True

    if updated:
        contact.updated_at = utcnow()
        await session.commit()
        await session.refresh(contact)

    return ContactRead.from_orm(contact)


@router.delete(
    "/{organization_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_contact(
    organization_id: int,
    contact_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await _get_organization_by_id(organization_id, session)
    contact = await _get_contact_by_id(
        contact_id=contact_id, organization_id=organization_id, session=session
    )
    await session.delete(contact)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
