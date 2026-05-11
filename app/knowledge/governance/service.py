"""Governance service (Plan 32 M2.3 / M2.4).

Assembles FacetStats from DB + composes alerts. Retains zero business
logic in the router — the router just awaits one entry point.

All aggregation queries bounded to the window (7d availability, 30d
coverage, configurable expiration). Heavy queries have indexes (chunk
events on (kb_id, event_type, created_at); no_result on (kb_id, created_at)).
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.knowledge.governance.health import (
    FacetStats,
    answer_quality_score,
    availability_score,
    chunk_quality_score,
    compose_health,
    coverage_score,
    freshness_score,
)
from app.knowledge.governance.models import (
    ChunkUsageEvent,
    RetrievalNoResultEvent,
)
from app.knowledge.governance.schemas import (
    DEFAULT_WEIGHTS,
    FacetScore,
    GovernanceAlert,
    GovernanceHealthResponse,
    GovernanceOverview,
    GovernanceOverviewItem,
    GovernanceWeights,
)
from app.knowledge.models import Chunk, Document, KnowledgeBase

logger = structlog.get_logger(__name__)

DEFAULT_EXPIRATION_DAYS = 90
LOW_QUALITY_THRESHOLD = 0.4  # composite < this → "low quality" alert
COLD_DAYS = 30
AVAILABILITY_WINDOW_DAYS = 7


class GovernanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public entry points ──────────────────────────────────────

    async def compute_health(
        self, kb_id: uuid.UUID, weights: GovernanceWeights | None = None,
    ) -> GovernanceHealthResponse:
        kb = await self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", str(kb_id))

        now = datetime.now(timezone.utc)
        stats = await self._gather_stats(kb, now)

        facet_tuples = {
            "chunk_quality": chunk_quality_score(stats),
            "coverage": coverage_score(stats),
            "freshness": freshness_score(stats),
            "availability": availability_score(stats),
            "answer_quality": answer_quality_score(stats),
        }
        w = (weights or GovernanceWeights()).normalized()
        health = compose_health(facet_tuples, w)

        facets = {
            k: FacetScore(score=score, weight=w[k], detail=detail)
            for k, (score, detail) in facet_tuples.items()
        }
        alerts = await self._collect_alerts(kb, stats, now)
        trend = await self._compute_trend(kb, now)

        # Plan 32 M2 — 顺手把健康分写回 KB 缓存字段，列表 API 零额外查询。
        # best-effort：失败不影响主返回，下次任务/详情页访问会再覆盖。
        try:
            await self.db.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.id == kb.id)
                .values(
                    health_score=int(round(health)),
                    health_score_updated_at=now,
                )
            )
            await self.db.commit()
        except Exception:
            logger.debug("health_score_writeback_failed", kb_id=str(kb.id), exc_info=True)

        return GovernanceHealthResponse(
            kb_id=kb.id,
            health_score=health,
            facets=facets,
            alerts=alerts,
            trend=trend,
            generated_at=now,
        )

    async def compute_overview(
        self, weights: GovernanceWeights | None = None,
    ) -> GovernanceOverview:
        """Cross-KB admin view — one card per KB."""
        now = datetime.now(timezone.utc)
        kbs = (await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.status == "active")
        )).scalars().all()
        items: list[GovernanceOverviewItem] = []
        for kb in kbs:
            try:
                resp = await self.compute_health(kb.id, weights)
            except Exception:
                continue
            items.append(GovernanceOverviewItem(
                kb_id=kb.id, kb_name=kb.name,
                health_score=resp.health_score,
                alerts_critical=sum(1 for a in resp.alerts if a.severity == "critical"),
                alerts_warning=sum(1 for a in resp.alerts if a.severity == "warning"),
            ))
        avg = round(sum(i.health_score for i in items) / len(items), 1) if items else 0.0
        return GovernanceOverview(kbs=items, avg_health_score=avg, generated_at=now)

    # ── FacetStats aggregation ───────────────────────────────────

    async def _gather_stats(
        self, kb: KnowledgeBase, now: datetime,
    ) -> FacetStats:
        cfg = kb.governance_config or {}
        expiration_days = int(cfg.get("expiration_threshold_days", DEFAULT_EXPIRATION_DAYS))
        cold_cutoff = now - timedelta(days=COLD_DAYS)
        stale_cutoff = now - timedelta(days=expiration_days)
        avail_cutoff = now - timedelta(days=AVAILABILITY_WINDOW_DAYS)

        # Chunk-level aggregates — Plan 39 跳过 review_excluded 内容（pending/rejected 不污染治理画像）
        row = (await self.db.execute(
            select(
                func.count(Chunk.id),
                func.avg(Chunk.quality_composite),
            ).where(
                Chunk.knowledge_base_id == kb.id,
                Chunk.review_excluded.is_(False),
            )
        )).one()
        total_chunks = int(row[0] or 0)
        avg_composite = float(row[1]) if row[1] is not None else None

        # Chunks hit in last 30d (via last_hit_at)
        hit_chunks = int((await self.db.execute(
            select(func.count(Chunk.id)).where(
                Chunk.knowledge_base_id == kb.id,
                Chunk.review_excluded.is_(False),
                Chunk.last_hit_at.isnot(None),
                Chunk.last_hit_at >= cold_cutoff,
            )
        )).scalar() or 0)

        # Plan 40 M2 — unit-level 统计走 unit_stats 抽象层（多 source_type 适配）
        from app.knowledge.governance.unit_stats import get_unit_stats
        unit_stats_result = await get_unit_stats(self.db, kb, stale_cutoff)
        total_docs = unit_stats_result.total_units
        stale_docs = unit_stats_result.stale_units

        # Availability: retrievals in last 7d.
        # "total_retrievals_7d" = unique messages (≈ retrievals) that hit
        # this KB — we approximate from chunk_usage_events (event_type=hit)
        # + retrieval_no_result_events within the window.
        hit_retrievals = int((await self.db.execute(
            select(func.count(func.distinct(ChunkUsageEvent.message_id))).where(
                ChunkUsageEvent.kb_id == kb.id,
                ChunkUsageEvent.event_type == "hit",
                ChunkUsageEvent.created_at >= avail_cutoff,
            )
        )).scalar() or 0)
        no_result = int((await self.db.execute(
            select(func.count(RetrievalNoResultEvent.id)).where(
                RetrievalNoResultEvent.kb_id == kb.id,
                RetrievalNoResultEvent.created_at >= avail_cutoff,
            )
        )).scalar() or 0)
        total_retrievals = hit_retrievals + no_result

        # Plan 25 answer quality — 取 answer-layer 指标的 7d 平均
        from app.knowledge.evaluation.models import MessageEvaluation
        answer_metrics = (
            "faithfulness", "answer_relevancy", "hallucination", "citation_accuracy",
        )
        ans_row = (await self.db.execute(
            select(func.avg(MessageEvaluation.score), func.count(MessageEvaluation.id))
            .where(
                MessageEvaluation.kb_id == kb.id,
                MessageEvaluation.metric.in_(answer_metrics),
                MessageEvaluation.evaluated_at >= avail_cutoff,
            )
        )).one()
        answer_avg = float(ans_row[0]) if ans_row[0] is not None else None
        answer_samples = int(ans_row[1] or 0)

        return FacetStats(
            total_chunks=total_chunks,
            avg_quality_composite=avg_composite,
            hit_chunks_30d=hit_chunks,
            total_docs=total_docs,
            stale_docs=stale_docs,
            total_retrievals_7d=total_retrievals,
            successful_retrievals_7d=hit_retrievals,
            answer_quality_avg=answer_avg,
            answer_quality_samples=answer_samples,
        )

    # ── Alerts ───────────────────────────────────────────────────

    async def _collect_alerts(
        self, kb: KnowledgeBase, stats: FacetStats, now: datetime,
    ) -> list[GovernanceAlert]:
        alerts: list[GovernanceAlert] = []
        cold_cutoff = now - timedelta(days=COLD_DAYS)
        cfg = kb.governance_config or {}
        expiration_days = int(cfg.get("expiration_threshold_days", DEFAULT_EXPIRATION_DAYS))
        stale_cutoff = now - timedelta(days=expiration_days)

        # Stale units (Plan 40 M2 — 多 source_type 适配)
        if stats.stale_docs > 0:
            from app.knowledge.governance.unit_stats import get_stale_unit_preview
            preview_rows = await get_stale_unit_preview(self.db, kb, stale_cutoff, limit=10)
            unit_label = "条目" if kb.source_type == "entry" else "文档"
            alerts.append(GovernanceAlert(
                severity="warning" if stats.stale_docs < 0.3 * max(stats.total_docs, 1) else "critical",
                kind="stale_docs",  # alert kind 保留兼容（前端按 KB.source_type 选文案）
                title=f"{stats.stale_docs} 份{unit_label}超过 {expiration_days} 天未更新",
                count=stats.stale_docs,
                preview=[
                    {"id": str(r.unit_id), "title": r.title, "updated_at": r.updated_at.isoformat()}
                    for r in preview_rows
                ],
                action_href=f"/knowledge/{kb.id}?filter=stale",
            ))

        # Low-quality chunks (composite < threshold) — Plan 39 跳过 review_excluded
        low_q_count = int((await self.db.execute(
            select(func.count(Chunk.id)).where(
                Chunk.knowledge_base_id == kb.id,
                Chunk.review_excluded.is_(False),
                Chunk.quality_composite.isnot(None),
                Chunk.quality_composite < LOW_QUALITY_THRESHOLD,
            )
        )).scalar() or 0)
        if low_q_count > 0:
            low_q_rows = (await self.db.execute(
                select(Chunk.id, Chunk.quality_composite, Chunk.content)
                .where(
                    Chunk.knowledge_base_id == kb.id,
                    Chunk.review_excluded.is_(False),
                    Chunk.quality_composite.isnot(None),
                    Chunk.quality_composite < LOW_QUALITY_THRESHOLD,
                )
                .order_by(Chunk.quality_composite.asc())
                .limit(5)
            )).all()
            alerts.append(GovernanceAlert(
                severity="warning",
                kind="low_quality_chunks",
                title=f"{low_q_count} 个 chunk 综合评分 < {LOW_QUALITY_THRESHOLD}",
                count=low_q_count,
                preview=[
                    {
                        "id": str(r[0]),
                        "score": round(float(r[1]), 3),
                        "preview": (r[2] or "")[:120],
                    }
                    for r in low_q_rows
                ],
                action_href=None,
            ))

        # Cold chunks — never hit OR no hit in last 30d (Plan 39 跳过 review_excluded)
        cold_count = int((await self.db.execute(
            select(func.count(Chunk.id)).where(
                Chunk.knowledge_base_id == kb.id,
                Chunk.review_excluded.is_(False),
                (Chunk.last_hit_at.is_(None)) | (Chunk.last_hit_at < cold_cutoff),
            )
        )).scalar() or 0)
        if cold_count > 0 and stats.total_chunks > 0 and cold_count / stats.total_chunks > 0.5:
            # Only alert when more than half are cold — some cold is normal,
            # especially for newly imported KBs.
            alerts.append(GovernanceAlert(
                severity="info",
                kind="cold_chunks",
                title=f"{cold_count} 个 chunk 最近 30 天未被检索（占 {round(cold_count / stats.total_chunks * 100)}%）",
                count=cold_count,
                preview=[],
                action_href=None,
            ))

        # Knowledge gap — clustered by exact-normalized query (simple first
        # pass; full embedding clustering is P3)
        gap_rows = (await self.db.execute(
            select(RetrievalNoResultEvent.query)
            .where(
                RetrievalNoResultEvent.kb_id == kb.id,
                RetrievalNoResultEvent.created_at >= now - timedelta(days=30),
            )
        )).scalars().all()
        if gap_rows:
            counter = Counter(q.strip().casefold() for q in gap_rows if q)
            top_gaps = counter.most_common(10)
            alerts.append(GovernanceAlert(
                severity="info" if len(top_gaps) < 3 else "warning",
                kind="knowledge_gap",
                title=f"最近 30 天有 {len(gap_rows)} 次检索无命中（{len(counter)} 种不同查询）",
                count=len(gap_rows),
                preview=[{"query": q, "count": n} for q, n in top_gaps],
                action_href=None,
            ))

        # Redundancy (Plan 26 M2) — 读 chunk_redundancy_pairs，Top-N 代表对
        from app.knowledge.coverage.models import ChunkRedundancyPair
        redundancy_count = int((await self.db.execute(
            select(func.count(ChunkRedundancyPair.id)).where(
                ChunkRedundancyPair.kb_id == kb.id,
            )
        )).scalar() or 0)
        if redundancy_count > 0:
            top_rows = (await self.db.execute(
                select(
                    ChunkRedundancyPair.chunk_a_id,
                    ChunkRedundancyPair.chunk_b_id,
                    ChunkRedundancyPair.similarity,
                )
                .where(ChunkRedundancyPair.kb_id == kb.id)
                .order_by(ChunkRedundancyPair.similarity.desc())
                .limit(10)
            )).all()
            chunk_ids = {r[0] for r in top_rows} | {r[1] for r in top_rows}
            content_rows = (await self.db.execute(
                select(Chunk.id, Chunk.content).where(Chunk.id.in_(chunk_ids))
            )).all()
            content_map = {cid: (text or "")[:120] for cid, text in content_rows}
            severity = (
                "warning" if redundancy_count / max(stats.total_chunks, 1) > 0.1
                else "info"
            )
            alerts.append(GovernanceAlert(
                severity=severity,
                kind="redundancy",
                title=f"检测到 {redundancy_count} 对高相似切片（相似度 ≥ 0.92）",
                count=redundancy_count,
                preview=[
                    {
                        "a_id": str(r[0]),
                        "b_id": str(r[1]),
                        "similarity": round(float(r[2]), 3),
                        "a_preview": content_map.get(r[0], ""),
                        "b_preview": content_map.get(r[1], ""),
                    }
                    for r in top_rows
                ],
                action_href=None,
            ))

        return alerts

    # ── Trend (7d) ───────────────────────────────────────────────

    async def _compute_trend(
        self, kb: KnowledgeBase, now: datetime,
    ) -> dict:
        """Daily aggregates for the last 7 days — 'hits' and 'adopted'
        per day. Frontend renders as sparkline.
        """
        since = now - timedelta(days=7)
        rows = (await self.db.execute(
            select(
                func.date_trunc("day", ChunkUsageEvent.created_at).label("day"),
                ChunkUsageEvent.event_type,
                func.count(),
            )
            .where(
                ChunkUsageEvent.kb_id == kb.id,
                ChunkUsageEvent.created_at >= since,
                ChunkUsageEvent.event_type.in_(("hit", "adopted")),
            )
            .group_by("day", ChunkUsageEvent.event_type)
            .order_by("day")
        )).all()
        hits: dict[str, int] = {}
        adopted: dict[str, int] = {}
        for day, etype, count in rows:
            bucket = hits if etype == "hit" else adopted
            bucket[day.date().isoformat()] = int(count)
        # Fill 7 days with zeros where missing
        series_days = [(now - timedelta(days=i)).date().isoformat() for i in range(6, -1, -1)]
        return {
            "hits": [{"t": d, "v": hits.get(d, 0)} for d in series_days],
            "adopted": [{"t": d, "v": adopted.get(d, 0)} for d in series_days],
        }
