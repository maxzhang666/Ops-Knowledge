"""Unit tests for Plan 32 M2 health facets + weight normalization."""
from __future__ import annotations

from app.knowledge.governance.health import (
    FacetStats,
    availability_score,
    chunk_quality_score,
    compose_health,
    coverage_score,
    freshness_score,
)
from app.knowledge.governance.schemas import GovernanceWeights


# ─── chunk_quality ────────────────────────────────────────────────

def test_chunk_quality_no_chunks_is_zero():
    # 完全没切片 → 0 分（空 KB 不存在"质量"）
    score, detail = chunk_quality_score(FacetStats(total_chunks=0, avg_quality_composite=None))
    assert score == 0.0
    assert detail["empty"] is True


def test_chunk_quality_chunks_exist_but_unscored_is_neutral_50():
    # 有切片但尚未评分 → neutral 50（冷启动）
    score, detail = chunk_quality_score(FacetStats(total_chunks=10, avg_quality_composite=None))
    assert score == 50.0
    assert detail["avg"] is None
    assert detail["total_chunks"] == 10


def test_chunk_quality_reflects_avg_composite():
    score, _ = chunk_quality_score(FacetStats(total_chunks=5, avg_quality_composite=0.72))
    assert score == 72.0


def test_chunk_quality_clamps_out_of_range():
    # Should never be above 100 even if composite somehow exceeds 1
    high, _ = chunk_quality_score(FacetStats(total_chunks=5, avg_quality_composite=1.5))
    assert high == 100.0
    low, _ = chunk_quality_score(FacetStats(total_chunks=5, avg_quality_composite=-0.2))
    assert low == 0.0


# ─── coverage ─────────────────────────────────────────────────────

def test_coverage_zero_chunks_is_zero():
    score, _ = coverage_score(FacetStats(total_chunks=0, hit_chunks_30d=0))
    assert score == 0.0


def test_coverage_all_hit_is_100():
    score, detail = coverage_score(FacetStats(total_chunks=20, hit_chunks_30d=20))
    assert score == 100.0
    assert detail["cold_chunks"] == 0


def test_coverage_partial():
    score, detail = coverage_score(FacetStats(total_chunks=10, hit_chunks_30d=3))
    assert score == 30.0
    assert detail["cold_chunks"] == 7


# ─── freshness ────────────────────────────────────────────────────

def test_freshness_no_docs_is_zero():
    # 没文档 = 空 KB → 0 分（不再掩盖空状态）
    score, detail = freshness_score(FacetStats(total_docs=0, stale_docs=0))
    assert score == 0.0
    assert detail["empty"] is True


def test_freshness_no_stale_is_100():
    score, _ = freshness_score(FacetStats(total_docs=10, stale_docs=0))
    assert score == 100.0


def test_freshness_half_stale():
    score, _ = freshness_score(FacetStats(total_docs=10, stale_docs=5))
    assert score == 50.0


def test_freshness_all_stale_is_zero():
    score, _ = freshness_score(FacetStats(total_docs=10, stale_docs=10))
    assert score == 0.0


# ─── availability ─────────────────────────────────────────────────

def test_availability_empty_kb_is_zero():
    # 空 KB（无 chunks 且无 docs）→ 0 分
    score, detail = availability_score(
        FacetStats(
            total_chunks=0, total_docs=0,
            total_retrievals_7d=0, successful_retrievals_7d=0,
        )
    )
    assert score == 0.0
    assert detail["empty"] is True


def test_availability_cold_start_with_content_is_neutral_100():
    # 有内容但无流量 → neutral 100（冷启动不惩罚）
    score, detail = availability_score(
        FacetStats(
            total_chunks=20, total_docs=3,
            total_retrievals_7d=0, successful_retrievals_7d=0,
        )
    )
    assert score == 100.0
    assert detail["success_rate"] is None


def test_availability_all_successful():
    score, _ = availability_score(
        FacetStats(
            total_chunks=10, total_docs=2,
            total_retrievals_7d=50, successful_retrievals_7d=50,
        )
    )
    assert score == 100.0


def test_availability_partial_success():
    score, detail = availability_score(
        FacetStats(
            total_chunks=10, total_docs=2,
            total_retrievals_7d=20, successful_retrievals_7d=15,
        )
    )
    assert score == 75.0
    assert detail["success_rate"] == 0.75


# ─── compose_health ───────────────────────────────────────────────

def test_empty_kb_composite_is_zero():
    """空 KB 整体健康分必须是 0（修复 63 分假象）"""
    s = FacetStats()  # 全 0
    facets = {
        "chunk_quality": chunk_quality_score(s),
        "coverage": coverage_score(s),
        "freshness": freshness_score(s),
        "availability": availability_score(s),
    }
    weights = {"chunk_quality": 0.25, "coverage": 0.25, "freshness": 0.25, "availability": 0.25}
    assert compose_health(facets, weights) == 0.0


def test_compose_health_equal_weights():
    facets = {
        "chunk_quality": (80.0, {}),
        "coverage": (60.0, {}),
        "freshness": (100.0, {}),
        "availability": (90.0, {}),
    }
    weights = {"chunk_quality": 0.25, "coverage": 0.25, "freshness": 0.25, "availability": 0.25}
    # (80 + 60 + 100 + 90) / 4 = 82.5
    assert compose_health(facets, weights) == 82.5


def test_compose_health_skewed_weights():
    facets = {"chunk_quality": (100.0, {}), "coverage": (0.0, {}),
              "freshness": (0.0, {}), "availability": (0.0, {})}
    weights = {"chunk_quality": 1.0, "coverage": 0.0, "freshness": 0.0, "availability": 0.0}
    assert compose_health(facets, weights) == 100.0


def test_compose_health_missing_weight_defaults_zero():
    # If weights dict omits a facet, it contributes nothing (defensive).
    facets = {"chunk_quality": (100.0, {}), "coverage": (100.0, {})}
    weights = {"chunk_quality": 0.5}  # coverage weight missing → 0
    assert compose_health(facets, weights) == 50.0


# ─── GovernanceWeights.normalized ─────────────────────────────────

def test_weights_default_already_normalized():
    w = GovernanceWeights().normalized()
    assert round(sum(w.values()), 6) == 1.0


def test_weights_normalize_any_positive_sum():
    # 5 个维度同权 → 各 1/5
    w = GovernanceWeights(
        chunk_quality=0.5, coverage=0.5, freshness=0.5,
        availability=0.5, answer_quality=0.5,
    ).normalized()
    for v in w.values():
        assert abs(v - 0.2) < 1e-9


def test_weights_all_zero_falls_back_to_default():
    w = GovernanceWeights(
        chunk_quality=0, coverage=0, freshness=0, availability=0, answer_quality=0,
    ).normalized()
    # All zero → default 0.2 each (Plan 25 加入 answer_quality 后均分 5 维)
    assert w == {
        "chunk_quality": 0.2, "coverage": 0.2, "freshness": 0.2,
        "availability": 0.2, "answer_quality": 0.2,
    }


def test_weights_skewed_renormalize():
    w = GovernanceWeights(
        chunk_quality=0.4, coverage=0.1, freshness=0.2,
        availability=0.2, answer_quality=0.1,
    ).normalized()
    assert round(sum(w.values()), 6) == 1.0
    assert abs(w["chunk_quality"] - 0.4) < 1e-9
