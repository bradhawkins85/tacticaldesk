from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List, Optional

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    KnowledgeDocument,
    KnowledgeDocumentRevision,
    KnowledgeSpace,
    utcnow,
)

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _normalize_slug(source: str, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", source)
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = _SLUG_RE.sub("-", ascii_text)
    ascii_text = re.sub(r"-+", "-", ascii_text).strip("-")
    return ascii_text or fallback


async def _ensure_unique_space_slug(
    session: AsyncSession, slug: str, *, exclude_id: Optional[int] = None
) -> str:
    base_slug = slug
    candidate = base_slug
    suffix = 2
    while True:
        query = select(func.count()).select_from(KnowledgeSpace).where(
            KnowledgeSpace.slug == candidate
        )
        if exclude_id is not None:
            query = query.where(KnowledgeSpace.id != exclude_id)
        result = await session.execute(query)
        count = result.scalar_one()
        if count == 0:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


async def _ensure_unique_document_slug(
    session: AsyncSession,
    *,
    space_id: int,
    slug: str,
    exclude_id: Optional[int] = None,
) -> str:
    base_slug = slug
    candidate = base_slug
    suffix = 2
    while True:
        query = select(func.count()).select_from(KnowledgeDocument).where(
            KnowledgeDocument.space_id == space_id,
            KnowledgeDocument.slug == candidate,
        )
        if exclude_id is not None:
            query = query.where(KnowledgeDocument.id != exclude_id)
        result = await session.execute(query)
        count = result.scalar_one()
        if count == 0:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


async def list_spaces_with_counts(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        select(KnowledgeSpace, func.count(KnowledgeDocument.id))
        .outerjoin(KnowledgeDocument, KnowledgeDocument.space_id == KnowledgeSpace.id)
        .group_by(KnowledgeSpace.id)
        .order_by(KnowledgeSpace.name.asc())
    )
    summaries: list[dict[str, object]] = []
    for space, document_count in result.all():
        summaries.append(
            {
                "id": space.id,
                "name": space.name,
                "slug": space.slug,
                "description": space.description,
                "icon": space.icon,
                "is_private": bool(space.is_private),
                "document_count": int(document_count or 0),
                "created_at": space.created_at,
                "updated_at": space.updated_at,
            }
        )
    return summaries


async def get_space_by_slug(session: AsyncSession, slug: str) -> Optional[KnowledgeSpace]:
    result = await session.execute(
        select(KnowledgeSpace).where(KnowledgeSpace.slug == slug)
    )
    return result.scalar_one_or_none()


async def get_space_by_id(session: AsyncSession, space_id: int) -> Optional[KnowledgeSpace]:
    result = await session.execute(
        select(KnowledgeSpace).where(KnowledgeSpace.id == space_id)
    )
    return result.scalar_one_or_none()


async def create_space(
    session: AsyncSession,
    *,
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    icon: Optional[str] = None,
    is_private: bool | None = None,
) -> KnowledgeSpace:
    cleaned_name = name.strip()
    normalized_slug = _normalize_slug(slug or cleaned_name, fallback="space")
    unique_slug = await _ensure_unique_space_slug(session, normalized_slug)
    space = KnowledgeSpace(
        name=cleaned_name,
        slug=unique_slug,
        description=description.strip() if description else None,
        icon=icon.strip() if icon else None,
        is_private=bool(is_private),
    )
    session.add(space)
    await session.commit()
    await session.refresh(space)
    return space


async def update_space(
    session: AsyncSession,
    space: KnowledgeSpace,
    *,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    icon: Optional[str] = None,
    is_private: Optional[bool] = None,
) -> KnowledgeSpace:
    updated = False
    if name is not None:
        cleaned_name = name.strip()
        if cleaned_name and cleaned_name != space.name:
            space.name = cleaned_name
            updated = True
    if slug is not None:
        cleaned_slug_input = slug.strip()
        if cleaned_slug_input:
            normalized = _normalize_slug(cleaned_slug_input, fallback="space")
            unique_slug = await _ensure_unique_space_slug(
                session, normalized, exclude_id=space.id
            )
            if unique_slug != space.slug:
                space.slug = unique_slug
                updated = True
    if description is not None:
        cleaned_description = description.strip() or None
        if cleaned_description != space.description:
            space.description = cleaned_description
            updated = True
    if icon is not None:
        cleaned_icon = icon.strip() or None
        if cleaned_icon != space.icon:
            space.icon = cleaned_icon
            updated = True
    if is_private is not None and bool(is_private) != bool(space.is_private):
        space.is_private = bool(is_private)
        updated = True
    if updated:
        await session.commit()
        await session.refresh(space)
    return space


async def delete_space(session: AsyncSession, space: KnowledgeSpace) -> None:
    await session.delete(space)
    await session.commit()


async def _validate_parent(
    session: AsyncSession,
    *,
    space_id: int,
    document: Optional[KnowledgeDocument],
    parent_id: Optional[int],
) -> Optional[KnowledgeDocument]:
    if parent_id is None:
        return None
    if document is not None and parent_id == document.id:
        raise ValueError("A document cannot be its own parent.")
    parent = await session.get(KnowledgeDocument, parent_id)
    if parent is None or parent.space_id != space_id:
        raise ValueError("Parent document must belong to the same space.")
    if document is not None:
        ancestor = parent
        while ancestor is not None:
            if ancestor.id == document.id:
                raise ValueError("Cannot move a document beneath one of its descendants.")
            if ancestor.parent_id is None:
                break
            ancestor = await session.get(KnowledgeDocument, ancestor.parent_id)
    return parent


async def list_documents(
    session: AsyncSession,
    *,
    space_id: int,
    include_unpublished: bool = True,
) -> list[KnowledgeDocument]:
    query = select(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
    if not include_unpublished:
        query = query.where(KnowledgeDocument.is_published.is_(True))
    query = query.order_by(KnowledgeDocument.position.asc(), KnowledgeDocument.title.asc())
    result = await session.execute(query)
    return result.scalars().all()


def build_document_tree(documents: Iterable[KnowledgeDocument]) -> list[dict[str, object]]:
    nodes: dict[int, dict[str, object]] = {}
    children_map: dict[int | None, List[dict[str, object]]] = defaultdict(list)
    for document in documents:
        node = {
            "id": document.id,
            "title": document.title,
            "slug": document.slug,
            "is_published": bool(document.is_published),
            "position": document.position,
            "children": children_map[document.id],
        }
        nodes[document.id] = node
        children_map[document.parent_id].append(node)

    def sort_nodes(items: List[dict[str, object]]) -> None:
        items.sort(key=lambda item: (item["position"], item["title"].lower()))
        for item in items:
            sort_nodes(item["children"])

    roots = children_map[None]
    sort_nodes(roots)
    return roots


async def create_document(
    session: AsyncSession,
    *,
    space: KnowledgeSpace,
    title: str,
    content: str,
    summary: Optional[str] = None,
    slug: Optional[str] = None,
    parent_id: Optional[int] = None,
    position: Optional[int] = None,
    is_published: bool | None = None,
    created_by_id: Optional[int] = None,
) -> KnowledgeDocument:
    normalized_slug = _normalize_slug(slug or title, fallback="document")
    unique_slug = await _ensure_unique_document_slug(
        session, space_id=space.id, slug=normalized_slug
    )
    parent = await _validate_parent(
        session, space_id=space.id, document=None, parent_id=parent_id
    )
    if position is None:
        result = await session.execute(
            select(func.max(KnowledgeDocument.position)).where(
                KnowledgeDocument.space_id == space.id,
                KnowledgeDocument.parent_id == (parent.id if parent else None),
            )
        )
        max_position = result.scalar_one()
        position = 0 if max_position is None else int(max_position) + 1
    document = KnowledgeDocument(
        space_id=space.id,
        parent_id=parent.id if parent else None,
        title=title.strip(),
        slug=unique_slug,
        summary=summary.strip() if summary else None,
        content=content,
        is_published=bool(is_published) if is_published is not None else False,
        position=position,
        created_by_id=created_by_id,
    )
    if document.is_published:
        document.published_at = utcnow()
    session.add(document)
    await session.flush()
    revision = KnowledgeDocumentRevision(
        document_id=document.id,
        version=document.version,
        title=document.title,
        summary=document.summary,
        content=document.content,
        created_by_id=document.created_by_id,
    )
    session.add(revision)
    await session.commit()
    await session.refresh(document)
    return document


async def update_document(
    session: AsyncSession,
    document: KnowledgeDocument,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    summary: Optional[str] = None,
    slug: Optional[str] = None,
    parent_id: Optional[int] = None,
    parent_supplied: bool = False,
    position: Optional[int] = None,
    is_published: Optional[bool] = None,
    created_by_id: Optional[int] = None,
) -> KnowledgeDocument:
    updated = False
    revision_needed = False

    if title is not None:
        cleaned_title = title.strip()
        if cleaned_title and cleaned_title != document.title:
            document.title = cleaned_title
            updated = True
            revision_needed = True
    if content is not None and content != document.content:
        document.content = content
        updated = True
        revision_needed = True
    if summary is not None:
        cleaned_summary = summary.strip() or None
        if cleaned_summary != document.summary:
            document.summary = cleaned_summary
            updated = True
            revision_needed = True
    if slug is not None:
        cleaned_slug = slug.strip()
        if cleaned_slug:
            normalized_slug = _normalize_slug(cleaned_slug, fallback=document.slug)
            unique_slug = await _ensure_unique_document_slug(
                session,
                space_id=document.space_id,
                slug=normalized_slug,
                exclude_id=document.id,
            )
            if unique_slug != document.slug:
                document.slug = unique_slug
                updated = True
    if parent_supplied:
        if parent_id is None:
            if document.parent_id is not None:
                document.parent_id = None
                updated = True
        else:
            parent = await _validate_parent(
                session,
                space_id=document.space_id,
                document=document,
                parent_id=parent_id,
            )
            parent_key = parent.id if parent else None
            if parent_key != document.parent_id:
                document.parent_id = parent_key
                updated = True
    if position is not None and position != document.position:
        document.position = position
        updated = True
    if created_by_id is not None and created_by_id != document.created_by_id:
        document.created_by_id = created_by_id
        updated = True
    if is_published is not None and bool(is_published) != bool(document.is_published):
        document.is_published = bool(is_published)
        document.published_at = utcnow() if document.is_published else None
        updated = True

    if revision_needed:
        document.version += 1
        revision = KnowledgeDocumentRevision(
            document_id=document.id,
            version=document.version,
            title=document.title,
            summary=document.summary,
            content=document.content,
            created_by_id=document.created_by_id,
        )
        session.add(revision)

    if updated or revision_needed:
        await session.commit()
        await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, document: KnowledgeDocument) -> None:
    await session.delete(document)
    await session.commit()


async def list_revisions(
    session: AsyncSession, document_id: int
) -> list[KnowledgeDocumentRevision]:
    result = await session.execute(
        select(KnowledgeDocumentRevision)
        .where(KnowledgeDocumentRevision.document_id == document_id)
        .order_by(KnowledgeDocumentRevision.version.desc())
    )
    return result.scalars().all()


async def get_revision(
    session: AsyncSession, document_id: int, version: int
) -> Optional[KnowledgeDocumentRevision]:
    result = await session.execute(
        select(KnowledgeDocumentRevision).where(
            KnowledgeDocumentRevision.document_id == document_id,
            KnowledgeDocumentRevision.version == version,
        )
    )
    return result.scalar_one_or_none()
