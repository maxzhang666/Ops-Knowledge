"""Coverage API (Plan 26 T3)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.knowledge.coverage.models import ChunkCrossKBRedundancyPair, KBTopic
from app.knowledge.models import Chunk, KnowledgeBase

router = APIRouter(prefix="/knowledge", tags=["coverage"])


class TopicItem(BaseModel):
    cluster_id: int
    label: str
    size: int
    keywords: list[str] = []
    example_chunk_ids: list[str] = []
    generated_at: datetime


class TopicsResponse(BaseModel):
    kb_id: uuid.UUID
    topics: list[TopicItem]


@router.get("/{kb_id}/topics", response_model=TopicsResponse)
async def list_topics(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    rows = (await db.execute(
        select(KBTopic)
        .where(KBTopic.kb_id == kb_id)
        .order_by(KBTopic.size.desc())
    )).scalars().all()
    return TopicsResponse(
        kb_id=kb_id,
        topics=[
            TopicItem(
                cluster_id=r.cluster_id,
                label=r.label,
                size=r.size,
                keywords=list(r.keywords or []),
                example_chunk_ids=[str(x) for x in (r.example_chunk_ids or [])],
                generated_at=r.generated_at,
            )
            for r in rows
        ],
    )


# ── Plan 31 — Cross-KB redundancy admin endpoint ──────────────────


class CrossKBPairItem(BaseModel):
    kb_a_id: uuid.UUID
    kb_a_name: str
    kb_b_id: uuid.UUID
    kb_b_name: str
    chunk_a_id: uuid.UUID
    chunk_b_id: uuid.UUID
    similarity: float
    a_preview: str
    b_preview: str


class CrossKBResponse(BaseModel):
    items: list[CrossKBPairItem]


@router.get("/governance/cross-kb-redundancy", response_model=CrossKBResponse)
async def cross_kb_redundancy(
    _admin: User = require_role(UserRole.SYSTEM_ADMIN),
    limit: int = 50,
    min_similarity: float = 0.85,
    db: AsyncSession = Depends(get_db),
):
    """跨库重复对的 admin 视图 (Plan 31 M3)。"""
    rows = (await db.execute(
        select(ChunkCrossKBRedundancyPair)
        .where(ChunkCrossKBRedundancyPair.similarity >= min_similarity)
        .order_by(ChunkCrossKBRedundancyPair.similarity.desc())
        .limit(max(1, min(limit, 500)))
    )).scalars().all()
    if not rows:
        return CrossKBResponse(items=[])

    kb_ids = {r.kb_a_id for r in rows} | {r.kb_b_id for r in rows}
    kb_rows = (await db.execute(
        select(KnowledgeBase.id, KnowledgeBase.name).where(KnowledgeBase.id.in_(kb_ids))
    )).all()
    kb_names = {kid: name for kid, name in kb_rows}

    chunk_ids = {r.chunk_a_id for r in rows} | {r.chunk_b_id for r in rows}
    content_rows = (await db.execute(
        select(Chunk.id, Chunk.content).where(Chunk.id.in_(chunk_ids))
    )).all()
    content_map = {cid: (txt or "")[:160] for cid, txt in content_rows}

    return CrossKBResponse(items=[
        CrossKBPairItem(
            kb_a_id=r.kb_a_id, kb_a_name=kb_names.get(r.kb_a_id, str(r.kb_a_id)),
            kb_b_id=r.kb_b_id, kb_b_name=kb_names.get(r.kb_b_id, str(r.kb_b_id)),
            chunk_a_id=r.chunk_a_id, chunk_b_id=r.chunk_b_id,
            similarity=round(float(r.similarity), 4),
            a_preview=content_map.get(r.chunk_a_id, ""),
            b_preview=content_map.get(r.chunk_b_id, ""),
        )
        for r in rows
    ])
