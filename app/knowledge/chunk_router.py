import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.knowledge.chunk_service import ChunkService
from app.knowledge.schemas import ChunkResponse
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/chunks", tags=["chunks"])


class ChunkEditRequest(BaseModel):
    content: str = Field(..., min_length=1)


class ChunkSplitRequest(BaseModel):
    split_positions: list[int] = Field(..., min_length=1)


class ChunkMergeRequest(BaseModel):
    chunk_ids: list[uuid.UUID] = Field(..., min_length=2)


class ChunkAnnotateRequest(BaseModel):
    tags: list[str] | None = None
    notes: str | None = None


@router.get("", response_model=PaginatedResponse)
async def list_chunks(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    document_id: uuid.UUID | None = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    chunk_svc = ChunkService(db)
    items, total = await chunk_svc.list_chunks(
        kb_id, document_id, pagination.offset, pagination.page_size
    )
    return PaginatedResponse(
        items=[ChunkResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(
    kb_id: uuid.UUID,
    chunk_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    chunk_svc = ChunkService(db)
    return await chunk_svc.get_chunk(chunk_id)


@router.put("/{chunk_id}", response_model=ChunkResponse)
async def edit_chunk(
    kb_id: uuid.UUID,
    chunk_id: uuid.UUID,
    body: ChunkEditRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    chunk_svc = ChunkService(db)
    return await chunk_svc.edit_chunk(chunk_id, body.content, current_user.id)


@router.post("/{chunk_id}/split", response_model=list[ChunkResponse])
async def split_chunk(
    kb_id: uuid.UUID,
    chunk_id: uuid.UUID,
    body: ChunkSplitRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    chunk_svc = ChunkService(db)
    return await chunk_svc.split_chunk(chunk_id, body.split_positions, current_user.id)


@router.post("/merge", response_model=ChunkResponse)
async def merge_chunks(
    kb_id: uuid.UUID,
    body: ChunkMergeRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    chunk_svc = ChunkService(db)
    return await chunk_svc.merge_chunks(body.chunk_ids, current_user.id)


@router.delete("/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chunk(
    kb_id: uuid.UUID,
    chunk_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    chunk_svc = ChunkService(db)
    await chunk_svc.delete_chunk(chunk_id)


@router.patch("/{chunk_id}/annotate", response_model=ChunkResponse)
async def annotate_chunk(
    kb_id: uuid.UUID,
    chunk_id: uuid.UUID,
    body: ChunkAnnotateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    chunk_svc = ChunkService(db)
    return await chunk_svc.annotate_chunk(chunk_id, body.tags, body.notes)
