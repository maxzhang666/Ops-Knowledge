import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.auth.models import UserRole
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.core.exceptions import ConflictError
from app.department.service import DepartmentService
from app.core.tasks import safe_delay
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
    svc = KBService(db)
    if current_user.role == UserRole.SYSTEM_ADMIN:
        accessible_ids = None
    else:
        dept_svc = DepartmentService(db)
        accessible_ids = await dept_svc.get_accessible_resource_ids(current_user.id, "knowledge_base")
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


@router.post("/{kb_id}/update", response_model=KBResponse)
async def update_kb(
    kb_id: uuid.UUID,
    data: KBUpdate,
    current_user: CurrentUser,
    response: Response,
    db: AsyncSession = Depends(get_db),
    if_unmodified_since: str | None = Header(default=None, alias="If-Unmodified-Since"),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    # Optimistic concurrency: caller passes the updated_at they saw; if the KB
    # was modified between their read and this write, reject with 409.
    expected = _parse_http_date(if_unmodified_since) if if_unmodified_since else None
    try:
        updated = await svc.update_kb(kb_id, data, if_unmodified_since=expected)
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Surface latest mtime so the client can use it on the next write.
    response.headers["Last-Modified"] = _to_http_date(updated.updated_at)
    return updated


def _parse_http_date(value: str) -> datetime | None:
    """Parse RFC 7231 date or ISO-8601 string; return None on failure.

    Accepting both makes it friendly to typed front-end clients without
    forcing them to format RFC dates.
    """
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_http_date(dt: datetime) -> str:
    from email.utils import format_datetime
    return format_datetime(dt, usegmt=True)


@router.post("/{kb_id}/delete", status_code=status.HTTP_202_ACCEPTED)
async def delete_kb(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "full")
    await svc.mark_kb_deleting(kb_id)
    safe_delay(cascade_delete_kb, str(kb_id))
    return {"detail": "Knowledge base deletion initiated"}


@router.post("/{kb_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_kb_endpoint(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """重建整个 KB 的 milvus collection（drop + 全量 re-embed + atomic swap）。

    用途：
    - 清理孤儿向量（如历史 entry 编辑残留的旧向量）
    - 切换 embedding 模型后重建索引
    - milvus 数据损坏修复

    异步执行；返回 celery task_id 供查询进度。"""
    from app.knowledge.embedding.tasks import reindex_kb as reindex_task

    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    result = reindex_task.delay(str(kb_id))
    return {"task_id": result.id, "status": "accepted"}
