"""Milvus 治理 celery 任务：孤儿向量扫描 + 清理。

孤儿定义：milvus collection 中存在的 PK 不在 PG `chunks.id` 集合（同 KB 范围）。
触发场景：编辑 unit 重切片时旧 chunk 被删但 milvus 旧向量未同步删除（Plan 41
编辑路径修复后才覆盖；历史残留必须靠这套任务清理）。

供 system 域 endpoint 异步调用，celery AsyncResult 给前端轮询任务进度。
KB 级 redis 锁防并发：同一 KB 同时只能跑一个 scan/clean。
"""
from __future__ import annotations

import uuid

import redis
import structlog
from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.runtime_config import get_sync_runtime_config
from app.knowledge.milvus.service import MilvusService, kb_collection_name
from app.knowledge.models import Chunk

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _gov_lock_key(kb_id: str) -> str:
    return f"milvus_gov_lock:{kb_id}"


def _acquire_lock(kb_id: str, ttl: int = 600) -> bool:
    """KB 级互斥锁，确保 scan/clean 不会在同一 KB 并发。"""
    try:
        r = redis.from_url(settings.REDIS_URL)
        return bool(r.set(_gov_lock_key(kb_id), "1", nx=True, ex=ttl))
    except Exception:
        # redis 异常时放行（治理任务幂等，重复跑没副作用）
        return True


def _release_lock(kb_id: str) -> None:
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.delete(_gov_lock_key(kb_id))
    except Exception:
        pass


def _compute_orphans(kb_id: str, milvus_svc: MilvusService) -> dict:
    """同步计算孤儿向量：milvus 在册 - PG 在册 = orphans。

    返回 {milvus_count, pg_count, orphan_ids, collection_exists}。"""
    collection = kb_collection_name(kb_id)
    if not milvus_svc.collection_exists(collection):
        return {
            "milvus_count": 0,
            "pg_count": 0,
            "orphan_ids": [],
            "collection_exists": False,
        }

    milvus_ids = set(milvus_svc.list_ids(collection))
    engine = _get_sync_engine()
    with Session(engine) as session:
        pg_rows = session.execute(
            select(Chunk.id).where(Chunk.knowledge_base_id == uuid.UUID(kb_id))
        ).all()
        pg_ids = {str(row[0]) for row in pg_rows}

    orphan_ids = sorted(milvus_ids - pg_ids)
    return {
        "milvus_count": len(milvus_ids),
        "pg_count": len(pg_ids),
        "orphan_ids": orphan_ids,
        "collection_exists": True,
    }


@shared_task(
    bind=True,
    name="app.knowledge.milvus.governance_tasks.scan_orphan_vectors",
)
def scan_orphan_vectors(self, kb_id: str) -> dict:
    """诊断扫描，不删除。前端轮询 task 状态拿结果做 Confirm 提示。"""
    if not _acquire_lock(kb_id):
        return {
            "status": "skipped",
            "reason": "another_governance_task_running",
            "kb_id": kb_id,
        }
    runtime_cfg = get_sync_runtime_config()
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    try:
        result = _compute_orphans(kb_id, milvus_svc)
        logger.info(
            "milvus_scan_orphans_done",
            kb_id=kb_id,
            milvus_count=result["milvus_count"],
            pg_count=result["pg_count"],
            orphan_count=len(result["orphan_ids"]),
        )
        return {
            "status": "completed",
            "kb_id": kb_id,
            **result,
            # 仅返回前 200 个 id 给前端展示，避免 task result 过大
            "orphan_ids_preview": result["orphan_ids"][:200],
            "orphan_count": len(result["orphan_ids"]),
        }
    finally:
        milvus_svc.close()
        _release_lock(kb_id)


@shared_task(
    bind=True,
    name="app.knowledge.milvus.governance_tasks.clean_orphan_vectors",
)
def clean_orphan_vectors(self, kb_id: str, batch_size: int = 1000) -> dict:
    """重新扫描 + 删除。任务执行时即时计算 orphan_ids，不依赖前一次 scan
    的陈旧结果（避免 scan→clean 间隔有新 chunk 被误判清掉）。"""
    if not _acquire_lock(kb_id):
        return {
            "status": "skipped",
            "reason": "another_governance_task_running",
            "kb_id": kb_id,
        }
    runtime_cfg = get_sync_runtime_config()
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    try:
        result = _compute_orphans(kb_id, milvus_svc)
        if not result["collection_exists"]:
            return {
                "status": "skipped",
                "reason": "collection_not_found",
                "kb_id": kb_id,
            }
        orphan_ids = result["orphan_ids"]
        if not orphan_ids:
            logger.info("milvus_clean_orphans_noop", kb_id=kb_id)
            return {
                "status": "completed",
                "kb_id": kb_id,
                "deleted": 0,
                "milvus_count": result["milvus_count"],
                "pg_count": result["pg_count"],
            }

        collection = kb_collection_name(kb_id)
        deleted_total = 0
        for i in range(0, len(orphan_ids), batch_size):
            chunk_batch = orphan_ids[i : i + batch_size]
            milvus_svc.delete_by_ids(collection, chunk_batch)
            deleted_total += len(chunk_batch)
        logger.info(
            "milvus_clean_orphans_done",
            kb_id=kb_id, deleted=deleted_total,
        )
        return {
            "status": "completed",
            "kb_id": kb_id,
            "deleted": deleted_total,
            "milvus_count_before": result["milvus_count"],
            "pg_count": result["pg_count"],
        }
    finally:
        milvus_svc.close()
        _release_lock(kb_id)
