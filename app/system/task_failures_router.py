"""System 域 — Celery 任务失败管理 endpoints。

提供失败任务的可见性与重放能力（详见 spec 19 §16）。

权限：仅 system_admin。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import UserRole
from app.core.celery import celery_app
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.system.models import TaskFailure

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/system/celery",
    tags=["system", "task-failures"],
    dependencies=[require_role(UserRole.SYSTEM_ADMIN)],
)


class TaskFailureItem(BaseModel):
    id: uuid.UUID
    task_id: str | None
    task_name: str
    state: str
    exception: str | None
    retries: int
    kb_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    failed_at: datetime
    retried_at: datetime | None
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class TaskFailureDetail(TaskFailureItem):
    args_json: list | dict | None
    kwargs_json: dict | None
    traceback: str | None
    enqueued_at: datetime | None
    resolved_by: uuid.UUID | None


class RetryResponse(BaseModel):
    task_id: str
    status: str = "accepted"


class ResolveResponse(BaseModel):
    resolved_at: datetime


class PendingCount(BaseModel):
    count: int


@router.get("/failures", response_model=PaginatedResponse)
async def list_failures(
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    state: str | None = Query(None, description="FAILURE / UNREGISTERED / TIMEOUT"),
    task_name: str | None = Query(None, description="精确匹配 task name"),
    kb_id: uuid.UUID | None = Query(None),
    resolved: bool | None = Query(None, description="true=已处理 / false=未处理 / 省略=全部"),
    db: AsyncSession = Depends(get_db),
):
    """失败任务列表（按 failed_at 倒序）。"""
    base = select(TaskFailure)
    if state:
        base = base.where(TaskFailure.state == state)
    if task_name:
        base = base.where(TaskFailure.task_name == task_name)
    if kb_id:
        base = base.where(TaskFailure.kb_id == kb_id)
    if resolved is True:
        base = base.where(TaskFailure.resolved_at.is_not(None))
    elif resolved is False:
        base = base.where(TaskFailure.resolved_at.is_(None))

    total = int((await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0)
    rows = (await db.execute(
        base.order_by(TaskFailure.failed_at.desc())
        .offset(pagination.offset).limit(pagination.page_size)
    )).scalars().all()
    return PaginatedResponse(
        items=[
            TaskFailureItem.model_validate(r).model_dump(mode="json") for r in rows
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/failures/pending/count", response_model=PendingCount)
async def pending_count(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Header badge 数：最近 24h failed AND resolved_at IS NULL。

    用 24h 窗口避免历史欠账永远红；老的失败仍能在列表里看到。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = int((await db.execute(
        select(func.count(TaskFailure.id)).where(
            TaskFailure.failed_at >= cutoff,
            TaskFailure.resolved_at.is_(None),
        )
    )).scalar() or 0)
    return PendingCount(count=count)


@router.get("/failures/{failure_id}", response_model=TaskFailureDetail)
async def get_failure(
    failure_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    tf = await db.get(TaskFailure, failure_id)
    if tf is None:
        raise HTTPException(404, "Failure record not found")
    return TaskFailureDetail.model_validate(tf)


@router.post(
    "/failures/{failure_id}/retry",
    response_model=RetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failure(
    failure_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """重放失败任务：白名单校验（task_name 必须在当前 worker 已注册）→
    send_task 重新 enqueue → 原行 retried_at + resolved_at 自动 set。"""
    tf = await db.get(TaskFailure, failure_id)
    if tf is None:
        raise HTTPException(404, "Failure record not found")

    # 安全：task_name 必须在当前进程已注册（防注入任意 celery task）
    if tf.task_name not in celery_app.tasks:
        raise HTTPException(
            400,
            f"Task '{tf.task_name}' is not registered in this worker — "
            "cannot retry. Check celery.py include list.",
        )

    args = tf.args_json if isinstance(tf.args_json, list) else []
    kwargs = tf.kwargs_json if isinstance(tf.kwargs_json, dict) else {}
    result = celery_app.send_task(tf.task_name, args=args, kwargs=kwargs)

    now = datetime.now(timezone.utc)
    await db.execute(
        update(TaskFailure)
        .where(TaskFailure.id == failure_id)
        .values(
            retried_at=now,
            resolved_at=now,
            resolved_by=current_user.id,
        )
    )
    await db.commit()
    logger.info(
        "task_failure.retried",
        failure_id=str(failure_id),
        original_task_id=tf.task_id,
        new_task_id=result.id,
        task_name=tf.task_name,
        actor=str(current_user.id),
    )
    return RetryResponse(task_id=result.id)


@router.post(
    "/failures/{failure_id}/resolve",
    response_model=ResolveResponse,
)
async def resolve_failure(
    failure_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """手动标记已处理（不删行，留审计）。重放接口会自动 set 这个字段。"""
    tf = await db.get(TaskFailure, failure_id)
    if tf is None:
        raise HTTPException(404, "Failure record not found")
    if tf.resolved_at:
        return ResolveResponse(resolved_at=tf.resolved_at)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(TaskFailure)
        .where(TaskFailure.id == failure_id)
        .values(resolved_at=now, resolved_by=current_user.id)
    )
    await db.commit()
    logger.info(
        "task_failure.resolved",
        failure_id=str(failure_id), actor=str(current_user.id),
    )
    return ResolveResponse(resolved_at=now)
