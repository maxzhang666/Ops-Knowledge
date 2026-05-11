"""Milvus 治理同步查询 helper（async）。

供 system 域 endpoint 直接调用：
- get_overview(db) — 全量 KB collection 健康总览
- get_embedding_consistency(db, kb_id) — 单 KB 维度对账详情

不做删除/重建（那是 governance_tasks 的事）。聚合速度敏感，避免触发
embedding API（dim_probe），改读 ModelRegistry.vector_dim 缓存值。
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_config import get_runtime_config
from app.knowledge.milvus.service import MilvusService, kb_collection_name
from app.knowledge.models import Chunk, KnowledgeBase
from app.model.models import ModelRegistryEntry

logger = structlog.get_logger(__name__)


def _extract_collection_dim(desc: dict[str, Any] | None) -> int | None:
    """从 milvus describe_collection 输出里抽取向量字段维度。
    schema fields 中找 dtype = FLOAT_VECTOR 的字段，读 params.dim。"""
    if not desc:
        return None
    for f in desc.get("fields", []):
        params = f.get("params") or {}
        if "dim" in params:
            try:
                return int(params["dim"])
            except (TypeError, ValueError):
                continue
    return None


async def _get_kb_dim(db: AsyncSession, kb: KnowledgeBase) -> int | None:
    """从 ModelRegistry 读 KB 当前 embedding 模型的维度。
    优先 embedding_model_id（registry 直接指向）；fallback (provider_id, model_name)。"""
    if kb.embedding_model_id:
        row = (await db.execute(
            select(ModelRegistryEntry.vector_dim)
            .where(ModelRegistryEntry.id == kb.embedding_model_id)
        )).first()
        if row and row[0] is not None:
            return int(row[0])
    if kb.embedding_provider_id and kb.embedding_model_name:
        row = (await db.execute(
            select(ModelRegistryEntry.vector_dim)
            .where(
                ModelRegistryEntry.provider_id == kb.embedding_provider_id,
                ModelRegistryEntry.model_id == kb.embedding_model_name,
            )
        )).first()
        if row and row[0] is not None:
            return int(row[0])
    return None


async def _get_kb_health(
    db: AsyncSession, kb: KnowledgeBase, milvus: MilvusService,
) -> dict:
    collection = kb_collection_name(kb.id)
    exists = milvus.collection_exists(collection)

    milvus_count = 0
    milvus_dim: int | None = None
    if exists:
        try:
            stats = milvus.get_collection_stats(collection)
            milvus_count = int(stats.get("row_count", 0))
        except Exception:
            milvus_count = 0
        try:
            milvus_dim = _extract_collection_dim(milvus.describe_collection(collection))
        except Exception:
            milvus_dim = None

    pg_total = int((await db.execute(
        select(func.count(Chunk.id)).where(Chunk.knowledge_base_id == kb.id)
    )).scalar() or 0)
    pg_unembedded = int((await db.execute(
        select(func.count(Chunk.id)).where(
            Chunk.knowledge_base_id == kb.id,
            Chunk.vector_id.is_(None),
        )
    )).scalar() or 0)

    kb_dim = await _get_kb_dim(db, kb)
    dim_matches = (
        kb_dim is not None and milvus_dim is not None and kb_dim == milvus_dim
    )

    # 孤儿粗估：milvus 行数 - PG 行数（精确扫描走 celery 任务）
    orphan_estimate = max(0, milvus_count - pg_total) if exists else 0

    return {
        "kb_id": str(kb.id),
        "kb_name": kb.name,
        "source_type": kb.source_type,
        "collection_exists": exists,
        "milvus_count": milvus_count,
        "pg_count": pg_total,
        "pg_unembedded": pg_unembedded,
        "orphan_estimate": orphan_estimate,
        "kb_dim": kb_dim,
        "milvus_dim": milvus_dim,
        "dim_matches": dim_matches,
        "embedding_model_id": (
            str(kb.embedding_model_id) if kb.embedding_model_id else None
        ),
        "embedding_model_name": kb.embedding_model_name,
    }


async def get_overview(db: AsyncSession) -> list[dict]:
    """全量 KB 总览（按创建时间降序）。"""
    kbs = (await db.execute(
        select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
    )).scalars().all()
    if not kbs:
        return []
    cfg = await get_runtime_config(db)
    milvus = MilvusService(runtime_cfg=cfg)
    try:
        return [await _get_kb_health(db, kb, milvus) for kb in kbs]
    finally:
        milvus.close()


async def get_embedding_consistency(db: AsyncSession, kb_id: uuid.UUID) -> dict | None:
    """单 KB 维度对账详情：返回 None 表示 KB 不存在。"""
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        return None
    cfg = await get_runtime_config(db)
    milvus = MilvusService(runtime_cfg=cfg)
    try:
        return await _get_kb_health(db, kb, milvus)
    finally:
        milvus.close()
