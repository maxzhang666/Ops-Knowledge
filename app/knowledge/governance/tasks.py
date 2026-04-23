"""Governance Celery tasks (Plan 32 M1.6).

- ``chunk_score_rebuild`` (5 min) — find chunks with events in the
  window, aggregate denorm counters + quality_dynamic + quality_composite.
- ``events_retention`` (daily) — TODO M4; drop events > 90d.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.knowledge.governance.scoring import (
    ChunkStats, compute_composite, compute_dynamic,
)

logger = structlog.get_logger(__name__)

REBUILD_WINDOW_MINUTES = 10  # look back double the schedule interval to avoid edge misses


@shared_task(name="app.knowledge.governance.tasks.chunk_score_rebuild")
def chunk_score_rebuild() -> dict:
    return asyncio.run(_run_chunk_score_rebuild())


async def _run_chunk_score_rebuild(
    window_minutes: int = REBUILD_WINDOW_MINUTES,
) -> dict:
    from app.knowledge.governance.models import ChunkUsageEvent
    from app.knowledge.models import Chunk

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    updated = 0
    try:
        async with sm() as db:
            # 1. Dirty chunks — any event since cutoff
            dirty_rows = await db.execute(
                select(ChunkUsageEvent.chunk_id)
                .where(ChunkUsageEvent.created_at >= cutoff)
                .group_by(ChunkUsageEvent.chunk_id)
            )
            dirty_ids = [r[0] for r in dirty_rows.all()]
            if not dirty_ids:
                return {"updated": 0, "dirty": 0}

            # 2. Aggregate ALL-TIME event counts per chunk (Chunk denorm is
            #    a lifetime rollup; events table is the source of truth).
            agg = await db.execute(
                select(
                    ChunkUsageEvent.chunk_id,
                    ChunkUsageEvent.event_type,
                    func.count(),
                )
                .where(ChunkUsageEvent.chunk_id.in_(dirty_ids))
                .group_by(ChunkUsageEvent.chunk_id, ChunkUsageEvent.event_type)
            )
            counts: dict = {}
            for cid, etype, n in agg.all():
                counts.setdefault(cid, {})[etype] = n

            # 3. Also fetch last_hit_at / last_adopted_at timestamps
            last_ts = await db.execute(
                select(
                    ChunkUsageEvent.chunk_id,
                    ChunkUsageEvent.event_type,
                    func.max(ChunkUsageEvent.created_at),
                )
                .where(
                    ChunkUsageEvent.chunk_id.in_(dirty_ids),
                    ChunkUsageEvent.event_type.in_(("hit", "adopted")),
                )
                .group_by(ChunkUsageEvent.chunk_id, ChunkUsageEvent.event_type)
            )
            last_map: dict = {}
            for cid, etype, ts in last_ts.all():
                last_map.setdefault(cid, {})[etype] = ts

            # 4. Fetch static scores (needed for composite)
            static_rows = await db.execute(
                select(Chunk.id, Chunk.quality_score).where(Chunk.id.in_(dirty_ids))
            )
            static_map = {r[0]: r[1] for r in static_rows.all()}

            # 5. Recompute + bulk update
            for cid in dirty_ids:
                c = counts.get(cid, {})
                hit = int(c.get("hit", 0))
                adopted = int(c.get("adopted", 0))
                pos = int(c.get("feedback_positive", 0))
                neg = int(c.get("feedback_negative", 0))
                reverse = int(c.get("feedback_reverse", 0))
                # Net out reverse votes FIFO-style: reverse cancels the oldest
                # non-reverse feedback votes of either sign. Simple approximation
                # — half the reverse against pos, half against neg, bounded.
                cancel = min(reverse, pos + neg)
                if cancel > 0:
                    pos_cancel = min(cancel, pos)
                    neg_cancel = cancel - pos_cancel
                    pos = max(pos - pos_cancel, 0)
                    neg = max(neg - neg_cancel, 0)

                stats = ChunkStats(
                    hit=hit, adopted=adopted,
                    feedback_positive=pos, feedback_negative=neg,
                )
                dyn = compute_dynamic(stats)
                comp = compute_composite(static_map.get(cid), dyn, hit)

                await db.execute(
                    update(Chunk)
                    .where(Chunk.id == cid)
                    .values(
                        hit_count=hit,
                        adopted_count=adopted,
                        feedback_positive=pos,
                        feedback_negative=neg,
                        quality_dynamic=dyn,
                        quality_composite=comp,
                        last_hit_at=last_map.get(cid, {}).get("hit"),
                        last_adopted_at=last_map.get(cid, {}).get("adopted"),
                    )
                )
                updated += 1
            await db.commit()

        logger.info("chunk_score_rebuild_done", dirty=len(dirty_ids), updated=updated)
        return {"dirty": len(dirty_ids), "updated": updated}
    finally:
        await engine.dispose()
