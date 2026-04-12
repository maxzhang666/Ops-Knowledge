import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.department.service import DepartmentService
from app.knowledge.ingestion.tasks import cascade_delete_kb
from app.knowledge.schemas import KBCreate, KBResponse, KBUpdate
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
async def create_kb(
    data: KBCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.create_kb(data, current_user.id)
    return kb


@router.get("", response_model=PaginatedResponse)
async def list_kbs(
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    dept_svc = DepartmentService(db)
    accessible_ids = await dept_svc.get_accessible_resource_ids(current_user.id, "knowledge_base")
    svc = KBService(db)
    items, total = await svc.list_kbs(
        current_user.id, accessible_ids, pagination.offset, pagination.page_size
    )
    return PaginatedResponse(
        items=[KBResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{kb_id}", response_model=KBResponse)
async def get_kb(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)
    return kb


@router.put("/{kb_id}", response_model=KBResponse)
async def update_kb(
    kb_id: uuid.UUID,
    data: KBUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")
    return await svc.update_kb(kb_id, data)


@router.delete("/{kb_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_kb(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "full")
    await svc.mark_kb_deleting(kb_id)
    cascade_delete_kb.delay(str(kb_id))
    return {"detail": "Knowledge base deletion initiated"}
