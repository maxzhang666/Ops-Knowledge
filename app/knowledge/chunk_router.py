import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.knowledge.chunk_service import ChunkService
from app.knowledge.schemas import ChunkResponse
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/chunks", tags=["chunks"])


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
