"""System 域 — Milvus 治理 endpoints。

提供 RAG 双写一致性的运维能力：
- 全量 KB 概览（PG ↔ Milvus 对账）
- 孤儿向量诊断扫描 + 清理（异步 celery 任务）
- 单 KB 维度一致性检查
- 任务状态查询（celery AsyncResult 透传）

权限：仅 system_admin。
"""
from __future__ import annotations

import uuid

import structlog
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import UserRole
from app.core.celery import celery_app
from app.core.database import get_db
from app.knowledge.milvus.governance import (
    get_embedding_consistency,
    get_overview,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/system/milvus",
    tags=["system", "milvus-governance"],
    dependencies=[require_role(UserRole.SYSTEM_ADMIN)],
)


@router.get("/overview")
async def overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """全量 KB collection 健康度。每行字段见 governance._get_kb_health。"""
    items = await get_overview(db)
    return {"items": items}


@router.get("/{kb_id}/embedding_consistency")
async def embedding_consistency(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """单 KB 详细维度对账。返回与 overview 单行同结构的字典。"""
    result = await get_embedding_consistency(db, kb_id)
    if result is None:
        raise HTTPException(404, "Knowledge base not found")
    return result


@router.post("/{kb_id}/scan_orphans", status_code=status.HTTP_202_ACCEPTED)
async def scan_orphans_endpoint(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """异步触发孤儿扫描（仅诊断，不删除）。返回 task_id 供轮询。"""
    from app.knowledge.milvus.governance_tasks import scan_orphan_vectors
    result = scan_orphan_vectors.delay(str(kb_id))
    logger.info(
        "milvus.scan_orphans.enqueued",
        kb_id=str(kb_id), task_id=result.id, actor=str(current_user.id),
    )
    return {"task_id": result.id, "status": "accepted"}


@router.post("/{kb_id}/clean_orphans", status_code=status.HTTP_202_ACCEPTED)
async def clean_orphans_endpoint(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """异步触发孤儿清理（任务内重新扫描 + 删除，避免陈旧数据）。"""
    from app.knowledge.milvus.governance_tasks import clean_orphan_vectors
    result = clean_orphan_vectors.delay(str(kb_id))
    logger.info(
        "milvus.clean_orphans.enqueued",
        kb_id=str(kb_id), task_id=result.id, actor=str(current_user.id),
    )
    return {"task_id": result.id, "status": "accepted"}


@router.get("/task/{task_id}/status")
async def task_status(
    task_id: str,
    current_user: CurrentUser,
):
    """通用 celery 任务状态查询。前端轮询用：state ∈ {PENDING, STARTED,
    SUCCESS, FAILURE, RETRY, REVOKED}。完成时 result 字段携带任务返回值。"""
    res = AsyncResult(task_id, app=celery_app)
    payload: dict = {"task_id": task_id, "state": res.state}
    # 任务完成才有结果；失败则 result 是异常对象，转字符串
    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)
    return payload
