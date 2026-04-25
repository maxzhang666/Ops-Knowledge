"""Retrieval Recommendation engine (Plan 35 M3).

聚合 retrieval_logs (per-call) + chunk_usage_events (hit/adopted) 推算
每 (kb_id, query_type) 当前最优策略，用 dataclass 暴露给 API/Celery。

策略选择思路：
  * 总样本 < MIN_SAMPLES   ：使用 query_classifier 内置的"通用基线"
  * 命中率 < LOW_HIT_RATE   ：建议提高 top_k + 必开 rerank
  * 采纳率 > HIGH_ADOPT     ：当前策略稳定，仅微调
  * 否则：基于 hit/adopted 比例做小幅 BM25/向量权重调整
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.governance.models import ChunkUsageEvent
from app.knowledge.retrieval.models import RetrievalLog
from app.knowledge.retrieval.query_classifier import (
    QueryType,
    StrategyRecommendation,
    recommend_strategy,
)

MIN_SAMPLES = 10
LOW_HIT_RATE = 0.5
HIGH_ADOPT = 0.6
WINDOW_DAYS = 30


@dataclass
class RecommendationStats:
    sample_size: int
    hit_count: int
    no_result_count: int
    avg_result_count: float
    hit_rate: float
    adopted_via_events: int
    adopted_rate: float


@dataclass
class TunedRecommendation:
    base: StrategyRecommendation
    tuned: StrategyRecommendation
    stats: RecommendationStats
    note: str


def derive_recommendation(
    qtype: QueryType, stats: RecommendationStats,
) -> TunedRecommendation:
    """根据观测数据微调内置基线。"""
    base = recommend_strategy(qtype)
    bm25 = base.bm25_weight
    vec = base.vector_weight
    top_k = base.top_k
    rerank = base.rerank
    note = base.note

    if stats.sample_size < MIN_SAMPLES:
        # 数据不足 → 直接返回基线
        return TunedRecommendation(
            base=base,
            tuned=base,
            stats=stats,
            note=f"采样数 {stats.sample_size} 不足 {MIN_SAMPLES}，沿用基线策略",
        )

    if stats.hit_rate < LOW_HIT_RATE:
        top_k = min(base.top_k + 3, 12)
        rerank = True
        note = f"命中率 {stats.hit_rate:.2f} 偏低 — 已扩大 top_k 至 {top_k} 并强制 rerank"
    elif stats.adopted_rate > HIGH_ADOPT:
        # 稳定，无需大改
        note = f"采纳率 {stats.adopted_rate:.2f} 稳定，建议沿用基线"
    else:
        # 中间区间：依据 hit/adopt 微调权重，最多 ±0.1
        delta = round((stats.adopted_rate - 0.4) * 0.2, 2)
        bm25 = max(0.1, min(0.9, base.bm25_weight - delta))
        vec = round(1.0 - bm25, 2)
        note = (
            f"采纳率 {stats.adopted_rate:.2f}，建议向"
            f"{'向量' if delta > 0 else 'BM25'}方向微调"
        )

    tuned = StrategyRecommendation(
        bm25_weight=round(bm25, 2),
        vector_weight=round(vec, 2),
        top_k=top_k,
        rerank=rerank,
        note=note,
    )
    return TunedRecommendation(base=base, tuned=tuned, stats=stats, note=note)


# ── DB 聚合 ───────────────────────────────────────────────────────


async def gather_stats(
    db: AsyncSession,
    kb_id: uuid.UUID,
    qtype: QueryType,
    *,
    window_days: int = WINDOW_DAYS,
) -> RecommendationStats:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    log_row = (await db.execute(
        select(
            func.count(RetrievalLog.id),
            func.sum(case_when_pos(RetrievalLog.result_count, 0)),
            func.coalesce(func.avg(RetrievalLog.result_count), 0.0),
        ).where(
            RetrievalLog.kb_id == kb_id,
            RetrievalLog.query_type == qtype,
            RetrievalLog.created_at >= cutoff,
        )
    )).one()
    sample_size = int(log_row[0] or 0)
    hit_count = int(log_row[1] or 0)
    avg_results = float(log_row[2] or 0.0)
    no_result = sample_size - hit_count

    adopted_count = int((await db.execute(
        select(func.count(ChunkUsageEvent.id)).where(
            ChunkUsageEvent.kb_id == kb_id,
            ChunkUsageEvent.event_type == "adopted",
            ChunkUsageEvent.created_at >= cutoff,
        )
    )).scalar() or 0)
    adopted_rate = (adopted_count / sample_size) if sample_size > 0 else 0.0
    hit_rate = (hit_count / sample_size) if sample_size > 0 else 0.0
    return RecommendationStats(
        sample_size=sample_size,
        hit_count=hit_count,
        no_result_count=no_result,
        avg_result_count=round(avg_results, 2),
        hit_rate=round(hit_rate, 3),
        adopted_via_events=adopted_count,
        adopted_rate=round(adopted_rate, 3),
    )


def case_when_pos(col, default: int):
    """SUM(CASE WHEN col > 0 THEN 1 ELSE default END) — 简洁封装。"""
    from sqlalchemy import case
    return case((col > 0, 1), else_=default)


# ── 序列化用 ───────────────────────────────────────────────────────


def to_payload(reco: TunedRecommendation) -> dict:
    return {
        "base": asdict(reco.base),
        "tuned": asdict(reco.tuned),
        "stats": asdict(reco.stats),
        "note": reco.note,
    }
