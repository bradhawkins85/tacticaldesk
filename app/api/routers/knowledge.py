from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import KnowledgeDocument, KnowledgeSpace
from app.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentPublishRequest,
    KnowledgeDocumentRead,
    KnowledgeDocumentRevisionRead,
    KnowledgeDocumentTreeNode,
    KnowledgeDocumentUpdate,
    KnowledgeSpaceCreate,
    KnowledgeSpaceDetail,
    KnowledgeSpaceRead,
    KnowledgeSpaceUpdate,
)
from app.services.knowledge_base import (
    build_document_tree,
    create_document,
    create_space,
    delete_document,
    delete_space,
    get_revision,
    get_space_by_id,
    list_documents,
    list_revisions,
    list_spaces_with_counts,
    update_document,
    update_space,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])


async def _get_space_or_404(space_id: int, session: AsyncSession) -> KnowledgeSpace:
    space = await get_space_by_id(session, space_id)
    if space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return space


async def _get_document_or_404(
    document_id: int, session: AsyncSession
) -> KnowledgeDocument:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.get("/spaces", response_model=list[KnowledgeSpaceRead])
async def list_spaces(session: AsyncSession = Depends(get_session)) -> list[KnowledgeSpaceRead]:
    summaries = await list_spaces_with_counts(session)
    return [KnowledgeSpaceRead(**summary) for summary in summaries]


@router.post(
    "/spaces",
    response_model=KnowledgeSpaceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_space_endpoint(
    payload: KnowledgeSpaceCreate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeSpaceRead:
    space = await create_space(
        session,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        icon=payload.icon,
        is_private=payload.is_private,
    )
    document_summaries = await list_spaces_with_counts(session)
    for summary in document_summaries:
        if summary["id"] == space.id:
            return KnowledgeSpaceRead(**summary)
    return KnowledgeSpaceRead(
        id=space.id,
        name=space.name,
        slug=space.slug,
        description=space.description,
        icon=space.icon,
        is_private=bool(space.is_private),
        document_count=0,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


@router.get("/spaces/{space_id}", response_model=KnowledgeSpaceDetail)
async def get_space_detail(
    space_id: int,
    session: AsyncSession = Depends(get_session),
    include_unpublished: bool = True,
) -> KnowledgeSpaceDetail:
    space = await _get_space_or_404(space_id, session)
    documents = await list_documents(
        session, space_id=space.id, include_unpublished=include_unpublished
    )
    tree = build_document_tree(documents)
    return KnowledgeSpaceDetail(
        id=space.id,
        name=space.name,
        slug=space.slug,
        description=space.description,
        icon=space.icon,
        is_private=bool(space.is_private),
        document_count=len(documents),
        created_at=space.created_at,
        updated_at=space.updated_at,
        documents=[KnowledgeDocumentTreeNode(**node) for node in tree],
    )


@router.patch("/spaces/{space_id}", response_model=KnowledgeSpaceRead)
async def update_space_endpoint(
    space_id: int,
    payload: KnowledgeSpaceUpdate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeSpaceRead:
    space = await _get_space_or_404(space_id, session)
    data = payload.dict(exclude_unset=True)
    await update_space(
        session,
        space,
        name=data.get("name"),
        slug=data.get("slug"),
        description=data.get("description"),
        icon=data.get("icon"),
        is_private=data.get("is_private"),
    )
    summaries = await list_spaces_with_counts(session)
    for summary in summaries:
        if summary["id"] == space.id:
            return KnowledgeSpaceRead(**summary)
    return KnowledgeSpaceRead(
        id=space.id,
        name=space.name,
        slug=space.slug,
        description=space.description,
        icon=space.icon,
        is_private=bool(space.is_private),
        document_count=0,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


@router.delete("/spaces/{space_id}", response_class=Response)
async def delete_space_endpoint(
    space_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    space = await _get_space_or_404(space_id, session)
    await delete_space(session, space)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/spaces/{space_id}/documents",
    response_model=list[KnowledgeDocumentTreeNode],
)
async def list_space_documents(
    space_id: int,
    session: AsyncSession = Depends(get_session),
    include_unpublished: bool = True,
) -> list[KnowledgeDocumentTreeNode]:
    await _get_space_or_404(space_id, session)
    documents = await list_documents(
        session, space_id=space_id, include_unpublished=include_unpublished
    )
    tree = build_document_tree(documents)
    return [KnowledgeDocumentTreeNode(**node) for node in tree]


@router.post(
    "/spaces/{space_id}/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_endpoint(
    space_id: int,
    payload: KnowledgeDocumentCreate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeDocumentRead:
    space = await _get_space_or_404(space_id, session)
    try:
        document = await create_document(
            session,
            space=space,
            title=payload.title,
            content=payload.content,
            summary=payload.summary,
            slug=payload.slug,
            parent_id=payload.parent_id,
            position=payload.position,
            is_published=payload.is_published,
            created_by_id=payload.created_by_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return KnowledgeDocumentRead.from_orm(document)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentRead)
async def get_document_endpoint(
    document_id: int, session: AsyncSession = Depends(get_session)
) -> KnowledgeDocumentRead:
    document = await _get_document_or_404(document_id, session)
    return KnowledgeDocumentRead.from_orm(document)


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentRead)
async def update_document_endpoint(
    document_id: int,
    payload: KnowledgeDocumentUpdate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeDocumentRead:
    document = await _get_document_or_404(document_id, session)
    data = payload.dict(exclude_unset=True)
    try:
        document = await update_document(
            session,
            document,
            title=data.get("title"),
            content=data.get("content"),
            summary=data.get("summary"),
            slug=data.get("slug"),
            parent_id=data.get("parent_id"),
            parent_supplied="parent_id" in data,
            position=data.get("position"),
            is_published=data.get("is_published"),
            created_by_id=data.get("created_by_id"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return KnowledgeDocumentRead.from_orm(document)


@router.delete("/documents/{document_id}", response_class=Response)
async def delete_document_endpoint(
    document_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    document = await _get_document_or_404(document_id, session)
    await delete_document(session, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/publish",
    response_model=KnowledgeDocumentRead,
)
async def publish_document_endpoint(
    document_id: int,
    payload: KnowledgeDocumentPublishRequest,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeDocumentRead:
    document = await _get_document_or_404(document_id, session)
    document = await update_document(
        session,
        document,
        is_published=payload.is_published,
    )
    return KnowledgeDocumentRead.from_orm(document)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[KnowledgeDocumentRevisionRead],
)
async def list_document_versions(
    document_id: int, session: AsyncSession = Depends(get_session)
) -> list[KnowledgeDocumentRevisionRead]:
    await _get_document_or_404(document_id, session)
    revisions = await list_revisions(session, document_id)
    return [KnowledgeDocumentRevisionRead.from_orm(item) for item in revisions]


@router.get(
    "/documents/{document_id}/versions/{version}",
    response_model=KnowledgeDocumentRevisionRead,
)
async def get_document_version(
    document_id: int,
    version: int,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeDocumentRevisionRead:
    await _get_document_or_404(document_id, session)
    revision = await get_revision(session, document_id, version)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found",
        )
    return KnowledgeDocumentRevisionRead.from_orm(revision)
