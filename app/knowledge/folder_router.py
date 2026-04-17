import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.folder_service import FolderService
from app.knowledge.schemas import FolderCreate, FolderResponse, FolderTreeResponse, FolderUpdate
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/folders", tags=["folders"])


async def _check_kb_access(
    kb_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession, level: str = "view"
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, level)


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    kb_id: uuid.UUID,
    data: FolderCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_kb_access(kb_id, current_user, db, "edit")
    svc = FolderService(db)
    return await svc.create_folder(kb_id, data)


@router.get("", response_model=list[FolderTreeResponse])
async def get_folder_tree(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_kb_access(kb_id, current_user, db)
    svc = FolderService(db)
    return await svc.get_folder_tree(kb_id)


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    kb_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_kb_access(kb_id, current_user, db)
    svc = FolderService(db)
    return await svc.get_folder(folder_id)


@router.post("/{folder_id}/update", response_model=FolderResponse)
async def update_folder(
    kb_id: uuid.UUID,
    folder_id: uuid.UUID,
    data: FolderUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_kb_access(kb_id, current_user, db, "edit")
    svc = FolderService(db)
    return await svc.update_folder(folder_id, data)


@router.post("/{folder_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    kb_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _check_kb_access(kb_id, current_user, db, "edit")
    svc = FolderService(db)
    await svc.delete_folder(folder_id)
