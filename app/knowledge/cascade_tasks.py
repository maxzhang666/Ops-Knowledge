"""通用 unit 级联清理 — Plan 40 P15。

unit 删除路径：
  service.delete_unit(unit_type, unit_id):
    1. plugin.on_unit_deleted (同步：清理 plugin 独占副产物，如 MinIO 文件)
    2. enqueue cascade_delete_unit (异步)
       ├─ DELETE FROM chunks WHERE unit_type=? AND unit_id=?
       ├─ Milvus: 按 chunk_id 批量删除 vector points
       ├─ DELETE FROM <unit_table> WHERE id=?
       └─ 每步幂等；失败 3 次告警 system_admin

替代了 entry/document delete endpoint 内同步删除的旧路径。同步路径仍保留
（小数据量直接删更简单），大数据量场景调用此 task 异步。
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _get_sync_engine():
    return create_engine(settings.DATABASE_URL.replace("+asyncpg", "+psycopg"), pool_pre_ping=True)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="app.knowledge.cascade_tasks.cascade_delete_unit",
)
def cascade_delete_unit(self, unit_type: str, unit_id: str, kb_id: str) -> dict:
    """级联删除 unit 的 chunks + Milvus vectors + unit row。
    每步幂等，失败重试。"""
    from app.knowledge.milvus.service import MilvusService, kb_collection_name
    from app.knowledge.models import Chunk, Document, KnowledgeEntry

    engine = _get_sync_engine()
    try:
        # 1. 收集 chunk ids + vector ids
        with Session(engine) as session:
            rows = session.execute(
                select(Chunk.id, Chunk.vector_id).where(
                    Chunk.unit_type == unit_type,
                    Chunk.unit_id == uuid.UUID(unit_id),
                )
            ).all()
            chunk_uuids = [r[0] for r in rows]
            vector_ids = [r[1] for r in rows if r[1]]

        # 2. Milvus 批量删除（幂等：不存在的 vector 静默跳过）
        try:
            milvus_svc = MilvusService()
            try:
                collection = kb_collection_name(kb_id)
                if vector_ids and milvus_svc.collection_exists(collection):
                    # filter expr: id in [...]
                    id_strs = ", ".join(f'"{vid}"' for vid in vector_ids)
                    milvus_svc.delete_by_filter(collection, f"id in [{id_strs}]")
            finally:
                milvus_svc.close()
        except Exception as exc:
            logger.warning("milvus_delete_partial_fail", error=str(exc))

        # 3. PG 删 chunks + unit row（同事务）
        with Session(engine) as session:
            session.execute(
                delete(Chunk).where(
                    Chunk.unit_type == unit_type,
                    Chunk.unit_id == uuid.UUID(unit_id),
                )
            )
            if unit_type == "document":
                doc = session.get(Document, uuid.UUID(unit_id))
                if doc is not None:
                    session.delete(doc)
            elif unit_type == "entry":
                entry = session.get(KnowledgeEntry, uuid.UUID(unit_id))
                if entry is not None:
                    session.delete(entry)
            session.commit()

        logger.info(
            "cascade_delete_unit_done",
            unit_type=unit_type, unit_id=unit_id,
            chunks_deleted=len(chunk_uuids), vectors_deleted=len(vector_ids),
        )
        return {
            "status": "completed",
            "chunks": len(chunk_uuids),
            "vectors": len(vector_ids),
        }
    except Exception as exc:
        logger.error("cascade_delete_unit_failed", unit_type=unit_type, unit_id=unit_id, error=str(exc))
        # 第三次失败后告警 system_admin
        if self.request.retries >= self.max_retries:
            try:
                _notify_admin_cascade_failed(unit_type, unit_id, str(exc))
            except Exception:
                logger.debug("notify_admin_failed", exc_info=True)
        raise self.retry(exc=exc)
    finally:
        engine.dispose()


def _notify_admin_cascade_failed(unit_type: str, unit_id: str, error: str) -> None:
    """3 次重试失败后给 system_admin 写 Notification。"""
    from app.auth.models import User, UserRole
    from app.system.models import Notification

    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            admins = session.execute(
                select(User.id).where(User.role == UserRole.SYSTEM_ADMIN)
            ).scalars().all()
            for uid in admins:
                session.add(Notification(
                    user_id=uid,
                    type="cascade_delete_failed",
                    title=f"级联删除失败：{unit_type}/{unit_id}",
                    content=f"重试 3 次仍失败。Error: {error[:300]}。请运维介入清理残留。",
                    priority="high",
                    resource_type="knowledge_unit",
                    resource_id=uuid.UUID(unit_id),
                ))
            session.commit()
    finally:
        engine.dispose()
