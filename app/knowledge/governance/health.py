"""Health score computation (Plan 32 M2.2).

4 facet functions each return (score_0_100, detail_dict). Composition
is weighted average with normalized GovernanceWeights. Kept standalone
(no DB session inside) so weighting logic can be unit tested with
pre-computed facet stats.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FacetStats:
    # Chunk quality
    total_chunks: int = 0
    avg_quality_composite: float | None = None   # 0..1
    # Coverage
    hit_chunks_30d: int = 0                       # chunks hit in last 30d
    # Freshness
    total_docs: int = 0
    stale_docs: int = 0
    # Availability
    total_retrievals_7d: int = 0
    successful_retrievals_7d: int = 0             # hit > 0
    # Answer quality (Plan 25) — 7d avg of faithfulness / relevancy / hallucination / citation
    answer_quality_avg: float | None = None       # 0..1
    answer_quality_samples: int = 0


def chunk_quality_score(s: FacetStats) -> tuple[float, dict]:
    if s.total_chunks == 0:
        # 完全没有 chunk —— 不存在"质量"，直接 0 分
        return 0.0, {"avg": None, "total_chunks": 0, "empty": True}
    if s.avg_quality_composite is None:
        # 有 chunk 但尚未评分 —— 冷启动阶段，给中性 50
        # （等 chunk_score_rebuild 跑过会变成真实分）
        return 50.0, {"avg": None, "total_chunks": s.total_chunks}
    score = max(0.0, min(1.0, s.avg_quality_composite)) * 100
    return round(score, 1), {
        "avg": round(s.avg_quality_composite, 3),
        "total_chunks": s.total_chunks,
    }


def coverage_score(s: FacetStats) -> tuple[float, dict]:
    if s.total_chunks == 0:
        return 0.0, {"total_chunks": 0, "hit_chunks_30d": 0}
    ratio = s.hit_chunks_30d / s.total_chunks
    return round(min(ratio, 1.0) * 100, 1), {
        "total_chunks": s.total_chunks,
        "hit_chunks_30d": s.hit_chunks_30d,
        "cold_chunks": s.total_chunks - s.hit_chunks_30d,
    }


def freshness_score(s: FacetStats) -> tuple[float, dict]:
    if s.total_docs == 0:
        # 没文档 = 没内容可新鲜 → 0 分（不再给 100 掩盖空状态）
        return 0.0, {"total_docs": 0, "stale_docs": 0, "empty": True}
    ratio = 1.0 - (s.stale_docs / s.total_docs)
    return round(max(ratio, 0.0) * 100, 1), {
        "total_docs": s.total_docs,
        "stale_docs": s.stale_docs,
    }


def availability_score(s: FacetStats) -> tuple[float, dict]:
    if s.total_chunks == 0 and s.total_docs == 0:
        # 完全空的 KB —— 不存在"可用性"可言
        return 0.0, {"total": 0, "successful": 0, "success_rate": None, "empty": True}
    if s.total_retrievals_7d == 0:
        # 有内容但无流量 —— 冷启动，给中性 100
        # 低流量 KB 不该仅因无人查就被标为不可用
        return 100.0, {"total": 0, "successful": 0, "success_rate": None}
    rate = s.successful_retrievals_7d / s.total_retrievals_7d
    return round(rate * 100, 1), {
        "total": s.total_retrievals_7d,
        "successful": s.successful_retrievals_7d,
        "success_rate": round(rate, 3),
    }


def answer_quality_score(s: FacetStats) -> tuple[float, dict]:
    """Layer 4 — LLM-as-judge 7d 平均。无样本时返回 neutral 50（不因没数据扣分）。
    例外：完全空的 KB（无 chunks 且无 docs）返回 0，与其他 facet 一致 ——
    避免"刚建空 KB 显示 10 分"的误导（5 facet × 50 × 0.2 = 10）。"""
    if s.total_chunks == 0 and s.total_docs == 0:
        return 0.0, {"samples": 0, "avg": None, "empty": True}
    if s.answer_quality_samples <= 0 or s.answer_quality_avg is None:
        return 50.0, {"samples": 0, "avg": None, "empty": True}
    score = max(0.0, min(1.0, s.answer_quality_avg)) * 100
    return round(score, 1), {
        "samples": s.answer_quality_samples,
        "avg": round(s.answer_quality_avg, 3),
    }


def compose_health(
    facets: dict[str, tuple[float, dict]],
    weights: dict[str, float],
) -> float:
    """Weighted average of facet scores. Weights must already be normalized
    (sum to 1)."""
    total = 0.0
    for key, (score, _detail) in facets.items():
        total += score * weights.get(key, 0.0)
    return round(total, 1)
