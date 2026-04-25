"""Retrieval auto-tuning Celery beat (Plan 35 M3)."""
from __future__ import annotations

import asyncio
import uuid
from typing import get_args

import structlog
from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.knowledge.retrieval.query_classifier import QueryType
from app.knowledge.retrieval.recommender import (
    derive_recommendation, gather_stats, to_payload,
)

logger = structlog.get_logger(__name__)


@shared_task(name="app.knowledge.retrieval.tasks.recommendation_rebuild")
def recommendation_rebuild() -> dict:
    return asyncio.run(_run_rebuild())


async def _run_rebuild() -> dict:
    from app.knowledge.models import KnowledgeBase
    from app.knowledge.retrieval.models import RetrievalRecommendation

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    totals = {"kbs": 0, "recommendations": 0}
    qtypes: list[QueryType] = list(get_args(QueryType))
    try:
        async with sm() as db:
            kbs = (await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.status == "active")
            )).scalars().all()
            for kb in kbs:
                totals["kbs"] += 1
                # 删除旧建议（幂等覆盖）
                await db.execute(
                    delete(RetrievalRecommendation).where(
                        RetrievalRecommendation.kb_id == kb.id,
                    )
                )
                for qt in qtypes:
                    stats = await gather_stats(db, kb.id, qt)
                    reco = derive_recommendation(qt, stats)
                    db.add(RetrievalRecommendation(
                        kb_id=kb.id,
                        query_type=qt,
                        sample_size=stats.sample_size,
                        payload=to_payload(reco),
                    ))
                    totals["recommendations"] += 1
                await db.commit()
        logger.info("recommendation_rebuild_done", **totals)
        return totals
    finally:
        await engine.dispose()
