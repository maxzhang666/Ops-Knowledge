"""治理 unit_stats 抽象层 — Plan 40 M2.2。

按 KB.source_type 分支统计 unit-level 数据，屏蔽 documents / knowledge_entries /
未来其他 unit 表的差异。GovernanceService 不再硬编码 documents。

新加 source_type = 加一个分支函数即可，不改 governance 主流程。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import Document, KnowledgeBase, KnowledgeEntry


class UnitStats(BaseModel):
    """跨 source_type 通用 unit 统计。"""
    total_units: int
    stale_units: int


class UnitStaleRow(BaseModel):
    """治理告警 preview 用的过期 unit 单行。"""
    unit_id: uuid.UUID
    title: str
    updated_at: datetime


async def get_unit_stats(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime,
) -> UnitStats:
    """按 KB.source_type 路由到对应统计实现。"""
    if kb.source_type == "file":
        return await _file_unit_stats(db, kb, stale_cutoff)
    if kb.source_type == "entry":
        return await _entry_unit_stats(db, kb, stale_cutoff)
    # 未知 source_type 不应导致整个治理服务塌；返回 0 让面板显示但不报错
    return UnitStats(total_units=0, stale_units=0)


async def get_stale_unit_preview(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime, limit: int = 10,
) -> list[UnitStaleRow]:
    """治理告警 preview：取最早过期的 N 个 unit。"""
    if kb.source_type == "file":
        return await _file_stale_preview(db, kb, stale_cutoff, limit)
    if kb.source_type == "entry":
        return await _entry_stale_preview(db, kb, stale_cutoff, limit)
    return []


# ── 文件型实现（沿用现有 documents 查询路径） ──────────────────────


async def _file_unit_stats(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime,
) -> UnitStats:
    total = int((await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb.id,
            Document.is_archived.is_(False),
        )
    )).scalar() or 0)
    stale = int((await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb.id,
            Document.is_archived.is_(False),
            Document.updated_at < stale_cutoff,
        )
    )).scalar() or 0)
    return UnitStats(total_units=total, stale_units=stale)


async def _file_stale_preview(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime, limit: int,
) -> list[UnitStaleRow]:
    rows = (await db.execute(
        select(Document.id, Document.title, Document.updated_at)
        .where(
            Document.knowledge_base_id == kb.id,
            Document.is_archived.is_(False),
            Document.updated_at < stale_cutoff,
        )
        .order_by(Document.updated_at.asc())
        .limit(limit)
    )).all()
    return [
        UnitStaleRow(unit_id=r[0], title=r[1], updated_at=r[2])
        for r in rows
    ]


# ── 条目型实现 ─────────────────────────────────────────────────


async def _entry_unit_stats(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime,
) -> UnitStats:
    total = int((await db.execute(
        select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.knowledge_base_id == kb.id,
            KnowledgeEntry.is_archived.is_(False),
        )
    )).scalar() or 0)
    stale = int((await db.execute(
        select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.knowledge_base_id == kb.id,
            KnowledgeEntry.is_archived.is_(False),
            KnowledgeEntry.updated_at < stale_cutoff,
        )
    )).scalar() or 0)
    return UnitStats(total_units=total, stale_units=stale)


async def _entry_stale_preview(
    db: AsyncSession, kb: KnowledgeBase, stale_cutoff: datetime, limit: int,
) -> list[UnitStaleRow]:
    rows = (await db.execute(
        select(KnowledgeEntry.id, KnowledgeEntry.title, KnowledgeEntry.updated_at)
        .where(
            KnowledgeEntry.knowledge_base_id == kb.id,
            KnowledgeEntry.is_archived.is_(False),
            KnowledgeEntry.updated_at < stale_cutoff,
        )
        .order_by(KnowledgeEntry.updated_at.asc())
        .limit(limit)
    )).all()
    return [
        UnitStaleRow(unit_id=r[0], title=r[1], updated_at=r[2])
        for r in rows
    ]
