"""Spec 25 Plan E §7 — 标签治理统计 + endpoint。

KB 级标签健康度面板：
- tag_cloud: 字典 top-N canonical (按 usage_count)
- orphan_chunks: 无 chunk_tags 的 chunks 数 / 占比
- auto_tag_accept_ratio: 近 30 天 accept / (accept+reject)
- routing_usage / boost_usage: 近 30 天 retrieval_logs 中启用比例
- 全部计算都过滤 is_test=False 避免调参实验污染数据
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.models import Chunk, KnowledgeEntry
from app.knowledge.retrieval.models import RetrievalLog
from app.knowledge.service import KBService
from app.knowledge.tagging.models import AutoTagAction, TagDictionary


# ── Pydantic ─────────────────────────────────────────────────────


class TagCloudItem(BaseModel):
    canonical: str
    usage_count: int


class TagGovernanceOverview(BaseModel):
    # 字典统计
    dictionary_size: int
    deprecated_size: int
    tag_cloud: list[TagCloudItem]

    # chunk 覆盖
    total_chunks: int
    orphan_chunks: int
    orphan_ratio: float  # 0~1

    # entry 自动标签状态
    total_entries: int
    entries_with_auto_tags: int

    # 自动标签接受率（30 天滚动窗口）
    accept_count_30d: int
    reject_count_30d: int
    accept_ratio_30d: float | None  # null 表示窗口内无操作

    # 检索 tag 子系统使用情况（30 天滚动）
    retrieval_total_30d: int
    routing_used_30d: int
    boost_used_30d: int
    tag_filter_used_30d: int


# ── Stats ────────────────────────────────────────────────────────


async def get_tag_overview(
    db: AsyncSession, kb_id: uuid.UUID,
) -> TagGovernanceOverview:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # 字典：active / deprecated 计数 + top 20 cloud
    dict_size = int((await db.execute(
        select(func.count(TagDictionary.id)).where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(False),
        )
    )).scalar() or 0)
    deprecated_size = int((await db.execute(
        select(func.count(TagDictionary.id)).where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(True),
        )
    )).scalar() or 0)
    cloud_rows = (await db.execute(
        select(TagDictionary.canonical, TagDictionary.usage_count)
        .where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(False),
            TagDictionary.usage_count > 0,
        )
        .order_by(TagDictionary.usage_count.desc())
        .limit(20)
    )).all()
    tag_cloud = [
        TagCloudItem(canonical=c, usage_count=int(u))
        for c, u in cloud_rows
    ]

    # chunk 覆盖
    total_chunks = int((await db.execute(
        select(func.count(Chunk.id)).where(Chunk.knowledge_base_id == kb_id)
    )).scalar() or 0)
    # 孤儿：chunk_tags IS NULL OR cardinality(chunk_tags)=0
    orphan_chunks = int((await db.execute(
        select(func.count(Chunk.id)).where(
            Chunk.knowledge_base_id == kb_id,
            (Chunk.chunk_tags.is_(None)) | (func.cardinality(Chunk.chunk_tags) == 0),
        )
    )).scalar() or 0)
    orphan_ratio = (orphan_chunks / total_chunks) if total_chunks > 0 else 0.0

    # entry 自动标签状态
    total_entries = int((await db.execute(
        select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
        )
    )).scalar() or 0)
    entries_with_auto = int((await db.execute(
        select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            KnowledgeEntry.auto_tags.is_not(None),
            func.jsonb_array_length(KnowledgeEntry.auto_tags) > 0,
        )
    )).scalar() or 0)

    # 自动标签接受率（30 天）
    action_rows = (await db.execute(
        select(AutoTagAction.action, func.count(AutoTagAction.id))
        .where(
            AutoTagAction.kb_id == kb_id,
            AutoTagAction.created_at >= cutoff,
        )
        .group_by(AutoTagAction.action)
    )).all()
    accept_count = 0
    reject_count = 0
    for action, count in action_rows:
        if action == "accept":
            accept_count = int(count)
        elif action == "reject":
            reject_count = int(count)
    total_actions = accept_count + reject_count
    accept_ratio = accept_count / total_actions if total_actions > 0 else None

    # 检索 tag 子系统使用率（30 天，过滤 is_test=False）
    retrieval_total = int((await db.execute(
        select(func.count(RetrievalLog.id)).where(
            RetrievalLog.kb_id == kb_id,
            RetrievalLog.created_at >= cutoff,
            RetrievalLog.is_test.is_(False),
        )
    )).scalar() or 0)

    # JSONB 字段 boolean 提取：tag_signals->'routing_used' = true
    def _signal_eq_true(key: str):
        return cast(RetrievalLog.tag_signals[key].astext, JSONB) == cast("true", JSONB)

    routing_used = int((await db.execute(
        select(func.count(RetrievalLog.id)).where(
            RetrievalLog.kb_id == kb_id,
            RetrievalLog.created_at >= cutoff,
            RetrievalLog.is_test.is_(False),
            _signal_eq_true("routing_used"),
        )
    )).scalar() or 0)
    boost_used = int((await db.execute(
        select(func.count(RetrievalLog.id)).where(
            RetrievalLog.kb_id == kb_id,
            RetrievalLog.created_at >= cutoff,
            RetrievalLog.is_test.is_(False),
            _signal_eq_true("boost_active"),
        )
    )).scalar() or 0)
    tag_filter_used = int((await db.execute(
        select(func.count(RetrievalLog.id)).where(
            RetrievalLog.kb_id == kb_id,
            RetrievalLog.created_at >= cutoff,
            RetrievalLog.is_test.is_(False),
            _signal_eq_true("tag_filter_used"),
        )
    )).scalar() or 0)

    return TagGovernanceOverview(
        dictionary_size=dict_size,
        deprecated_size=deprecated_size,
        tag_cloud=tag_cloud,
        total_chunks=total_chunks,
        orphan_chunks=orphan_chunks,
        orphan_ratio=round(orphan_ratio, 4),
        total_entries=total_entries,
        entries_with_auto_tags=entries_with_auto,
        accept_count_30d=accept_count,
        reject_count_30d=reject_count,
        accept_ratio_30d=round(accept_ratio, 4) if accept_ratio is not None else None,
        retrieval_total_30d=retrieval_total,
        routing_used_30d=routing_used,
        boost_used_30d=boost_used,
        tag_filter_used_30d=tag_filter_used,
    )


# ── Router ───────────────────────────────────────────────────────


router = APIRouter(
    prefix="/knowledge/{kb_id}/tag-governance",
    tags=["tag-governance"],
)


@router.get("/overview", response_model=TagGovernanceOverview)
async def overview_endpoint(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """KB 级标签治理总览。任何能访问 KB 的角色可读（含 viewer）。"""
    kb = await KBService(db).get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, "view",
    )
    return await get_tag_overview(db, kb_id)


# 静态检查兼容
_ = case  # 保留 import 以备后续指标扩展使用
