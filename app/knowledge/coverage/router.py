"""Coverage API (Plan 26 T3)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.coverage.models import KBTopic
from app.knowledge.models import KnowledgeBase

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
