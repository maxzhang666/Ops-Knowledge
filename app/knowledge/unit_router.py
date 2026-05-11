"""Plan 40 M2.4 — 多态 unit endpoints（跨 source_type 的 unit-level 操作）。

第一个落地：impact 分析（破坏性操作前的影响面预览）。
保留 ``POST /knowledge/{kb_id}/documents/{doc_id}/impact`` 为 deprecated alias
一个版本周期，路径内部 redirect。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.governance.models import ChunkUsageEvent
from app.knowledge.models import Chunk, Document, KnowledgeBase, KnowledgeEntry

router = APIRouter(prefix="/units", tags=["units"])

ALLOWED_UNIT_TYPES = {"document", "entry"}


class UnitImpactResponse(BaseModel):
    n_chunks: int
    hits_7d: int
    top_frequency_chunks: list[dict]
    active_conversations_7d: int


@router.post("/{unit_type}/{unit_id}/impact", response_model=UnitImpactResponse)
async def unit_impact(
    unit_type: str,
    unit_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UnitImpactResponse:
    """破坏性操作前的影响面预览：chunk 数、近期热度、波及会话。
    跨 source_type 通用：按 chunks 表多态 FK 查 chunks，再聚合 hits / 会话。"""
    if unit_type not in ALLOWED_UNIT_TYPES:
        raise HTTPException(400, f"unit_type must be one of {ALLOWED_UNIT_TYPES}")

    # 找到 unit 所属 KB（用于权限检查）
    if unit_type == "document":
        doc = await db.get(Document, unit_id)
        if doc is None:
            raise HTTPException(404, "Unit not found")
        kb_id = doc.knowledge_base_id
    elif unit_type == "entry":
        entry = await db.get(KnowledgeEntry, unit_id)
        if entry is None:
            raise HTTPException(404, "Unit not found")
        kb_id = entry.knowledge_base_id
    else:
        raise HTTPException(400, f"unit_type {unit_type} not yet supported")

    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    return await _compute_unit_impact(db, unit_type, unit_id)


async def _compute_unit_impact(
    db: AsyncSession, unit_type: str, unit_id: uuid.UUID,
) -> UnitImpactResponse:
    """跨 source_type 通用计算逻辑。
    沿用 document_router.document_impact 原算法（保持语义一致）："""
    from app.chat.models import Message

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    chunk_rows = (await db.execute(
        select(Chunk.id, Chunk.content).where(
            Chunk.unit_type == unit_type, Chunk.unit_id == unit_id,
        )
    )).all()
    chunk_ids = [c[0] for c in chunk_rows]

    hits_7d = 0
    top_rows: list[tuple] = []
    active_conversations = 0

    if chunk_ids:
        hits_7d = int((await db.execute(
            select(func.count(ChunkUsageEvent.id)).where(
                ChunkUsageEvent.chunk_id.in_(chunk_ids),
                ChunkUsageEvent.event_type == "hit",
                ChunkUsageEvent.created_at >= since,
            )
        )).scalar() or 0)

        # Top frequency chunks
        top_rows = (await db.execute(
            select(
                ChunkUsageEvent.chunk_id,
                func.count(ChunkUsageEvent.id).label("hit_count"),
            )
            .where(
                ChunkUsageEvent.chunk_id.in_(chunk_ids),
                ChunkUsageEvent.event_type == "hit",
                ChunkUsageEvent.created_at >= since,
            )
            .group_by(ChunkUsageEvent.chunk_id)
            .order_by(func.count(ChunkUsageEvent.id).desc())
            .limit(5)
        )).all()

        # 会话波及：扫 message.metadata_.retrieval_chunks JSONB 引用到本 unit
        # 任一 chunk 的不同 conversation。沿用 document_impact 原算法保持语义。
        id_strs = {str(c) for c in chunk_ids}
        msg_rows = (await db.execute(
            select(Message.conversation_id, Message.metadata_).where(
                Message.metadata_.isnot(None),
                Message.created_at >= since,
            )
        )).all()
        conv_set: set[uuid.UUID] = set()
        for conv_id, meta in msg_rows:
            if not isinstance(meta, dict):
                continue
            for ch in (meta.get("retrieval_chunks") or []):
                if str(ch.get("id") or "") in id_strs:
                    conv_set.add(conv_id)
                    break
        active_conversations = len(conv_set)

    chunk_content_map = {cid: (content or "")[:120] for cid, content in chunk_rows}
    top_frequency = [
        {
            "chunk_id": str(cid),
            "hit_count": int(n),
            "preview": chunk_content_map.get(cid, ""),
        }
        for cid, n in top_rows
    ]

    return UnitImpactResponse(
        n_chunks=len(chunk_ids),
        hits_7d=hits_7d,
        top_frequency_chunks=top_frequency,
        active_conversations_7d=active_conversations,
    )
