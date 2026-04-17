"""Quality overview API — aggregates static chunk quality + retrieval hits.

Spec `01-knowledge-engine.md §Layer 5` requires a quality dashboard. Phase 1a
ships the basic version: distribution of `quality_score` (static scorer output)
plus `hit_count` aggregates (driven by `retrieval/service.py`'s per-query
counter increment).
"""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.models import Chunk
from app.knowledge.service import KBService

router = APIRouter(prefix="/knowledge/{kb_id}/quality", tags=["quality"])


class QualityOverviewResponse(BaseModel):
    chunk_count: int
    avg_quality: float | None          # 0-1, null when no chunks
    quality_distribution: dict[str, int]  # {"high": n, "mid": n, "low": n, "unscored": n}
    total_hits: int                    # sum(hit_count) across all chunks
    hit_chunk_count: int               # number of chunks with hit_count > 0
    cold_chunk_count: int              # chunks with hit_count == 0 (never retrieved)
    top_hit_chunks: list[dict]         # top 5 by hit_count


@router.get("/overview", response_model=QualityOverviewResponse)
async def quality_overview(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = KBService(db)
    kb = await svc.get_kb(kb_id)
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    # Single aggregate query — avoids multiple round-trips.
    agg = (await db.execute(
        select(
            func.count(Chunk.id),
            func.avg(Chunk.quality_score),
            func.sum(Chunk.hit_count),
            func.sum(case((Chunk.hit_count > 0, 1), else_=0)),
            func.sum(case((Chunk.quality_score >= 0.8, 1), else_=0)),
            func.sum(case(((Chunk.quality_score >= 0.5) & (Chunk.quality_score < 0.8), 1), else_=0)),
            func.sum(case(((Chunk.quality_score != None) & (Chunk.quality_score < 0.5), 1), else_=0)),  # noqa: E711
            func.sum(case((Chunk.quality_score == None, 1), else_=0)),  # noqa: E711
        ).where(Chunk.knowledge_base_id == kb_id)
    )).one()

    count = agg[0] or 0
    avg = float(agg[1]) if agg[1] is not None else None
    total_hits = int(agg[2] or 0)
    hit_chunks = int(agg[3] or 0)
    high = int(agg[4] or 0)
    mid = int(agg[5] or 0)
    low = int(agg[6] or 0)
    unscored = int(agg[7] or 0)

    # Top 5 most-hit chunks — informs "cold vs hot" triage
    top_rows = (await db.execute(
        select(Chunk.id, Chunk.hit_count, Chunk.content)
        .where(Chunk.knowledge_base_id == kb_id, Chunk.hit_count > 0)
        .order_by(Chunk.hit_count.desc())
        .limit(5)
    )).all()

    return QualityOverviewResponse(
        chunk_count=count,
        avg_quality=avg,
        quality_distribution={
            "high": high,
            "mid": mid,
            "low": low,
            "unscored": unscored,
        },
        total_hits=total_hits,
        hit_chunk_count=hit_chunks,
        cold_chunk_count=max(count - hit_chunks, 0),
        top_hit_chunks=[
            {"id": str(r[0]), "hit_count": r[1], "preview": (r[2] or "")[:120]}
            for r in top_rows
        ],
    )
