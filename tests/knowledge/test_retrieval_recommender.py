"""Plan 35 M5 — recommender pure-function tests."""
from __future__ import annotations

from app.knowledge.retrieval.recommender import (
    HIGH_ADOPT, LOW_HIT_RATE, MIN_SAMPLES,
    RecommendationStats, derive_recommendation, to_payload,
)


def _stats(**kw) -> RecommendationStats:
    base = dict(
        sample_size=20, hit_count=10, no_result_count=10,
        avg_result_count=2.0, hit_rate=0.5,
        adopted_via_events=8, adopted_rate=0.4,
    )
    base.update(kw)
    return RecommendationStats(**base)


def test_below_min_samples_returns_baseline_unchanged():
    s = _stats(sample_size=MIN_SAMPLES - 1)
    r = derive_recommendation("concept", s)
    assert r.tuned == r.base
    assert "采样数" in r.note


def test_low_hit_rate_expands_top_k_and_forces_rerank():
    s = _stats(hit_rate=LOW_HIT_RATE - 0.1, sample_size=50)
    r = derive_recommendation("definition", s)
    assert r.tuned.top_k > r.base.top_k
    assert r.tuned.rerank is True


def test_top_k_capped_at_12():
    # base for 'concept' = 6; expanding by 3 → 9, cap doesn't kick in here
    s = _stats(hit_rate=0.1, sample_size=200)
    r = derive_recommendation("concept", s)
    assert r.tuned.top_k <= 12


def test_high_adopt_preserves_baseline_with_note():
    s = _stats(hit_rate=0.8, adopted_rate=HIGH_ADOPT + 0.1, sample_size=100)
    r = derive_recommendation("how_to", s)
    # 高采纳：除 note 外所有字段保持基线
    assert r.tuned.bm25_weight == r.base.bm25_weight
    assert r.tuned.vector_weight == r.base.vector_weight
    assert r.tuned.top_k == r.base.top_k
    assert r.tuned.rerank == r.base.rerank
    assert "稳定" in r.note


def test_mid_range_tilts_weights_within_bounds():
    s = _stats(hit_rate=0.7, adopted_rate=0.5, sample_size=80)
    r = derive_recommendation("how_to", s)  # base bm25=0.5
    # 应当向某一侧轻微倾斜，但保持归一
    assert 0.0 < r.tuned.bm25_weight < 1.0
    assert abs(r.tuned.bm25_weight + r.tuned.vector_weight - 1.0) < 1e-6


def test_to_payload_serializes_all_fields():
    r = derive_recommendation("concept", _stats(sample_size=50))
    payload = to_payload(r)
    assert "base" in payload
    assert "tuned" in payload
    assert "stats" in payload
    assert "note" in payload
    assert payload["base"]["bm25_weight"] >= 0
    assert payload["stats"]["sample_size"] == 50
