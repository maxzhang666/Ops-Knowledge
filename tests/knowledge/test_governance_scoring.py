"""Dynamic + composite score formula (Plan 32 M1.6)."""
import pytest

from app.knowledge.governance.scoring import (
    ChunkStats, compute_composite, compute_dynamic,
)


def _stats(hit=0, adopted=0, pos=0, neg=0):
    return ChunkStats(hit=hit, adopted=adopted, feedback_positive=pos, feedback_negative=neg)


# ── compute_dynamic ──────────────────────────────────────────────

def test_no_hit_returns_zero():
    assert compute_dynamic(_stats()) == 0.0


def test_hit_without_adopted_low_score():
    """Retrieved but never cited → low adoption, hit-component kicks in
    a little, neutral feedback → somewhere around 0.2."""
    s = compute_dynamic(_stats(hit=10))
    assert 0.10 <= s <= 0.35


def test_perfect_adoption_neutral_feedback():
    """Every retrieval adopted, no feedback → should land high but not 1."""
    s = compute_dynamic(_stats(hit=20, adopted=20))
    assert s >= 0.70


def test_positive_feedback_lifts_score():
    base = compute_dynamic(_stats(hit=10, adopted=5))
    with_positive = compute_dynamic(_stats(hit=10, adopted=5, pos=10))
    assert with_positive > base


def test_negative_feedback_depresses_score():
    base = compute_dynamic(_stats(hit=10, adopted=5))
    with_negative = compute_dynamic(_stats(hit=10, adopted=5, neg=10))
    assert with_negative < base


def test_mixed_feedback_neutralizes():
    """Equal pos + neg → feedback component at ~0.5 (neutral)."""
    s_mixed = compute_dynamic(_stats(hit=10, adopted=5, pos=5, neg=5))
    s_neutral = compute_dynamic(_stats(hit=10, adopted=5))
    assert abs(s_mixed - s_neutral) < 0.01


def test_bounded_in_unit_interval():
    """Any plausible input stays within [0, 1]."""
    for h, a, p, n in [(1, 1, 100, 0), (100, 100, 0, 100), (1000, 500, 20, 30)]:
        s = compute_dynamic(_stats(hit=h, adopted=a, pos=p, neg=n))
        assert 0.0 <= s <= 1.0


# ── compute_composite ────────────────────────────────────────────

def test_static_dominates_at_low_hit():
    """New chunk (hit=0): w_s=1.0, composite == static."""
    assert compute_composite(0.8, 0.3, hit=0) == pytest.approx(0.8)


def test_dynamic_dominates_past_60_hits():
    """hit=60: w_s = 0.4, so composite = 0.4*static + 0.6*dynamic."""
    got = compute_composite(1.0, 0.5, hit=60)
    assert got == pytest.approx(0.4 * 1.0 + 0.6 * 0.5)


def test_blend_monotonic():
    """More hits = more weight on dynamic."""
    results = [compute_composite(1.0, 0.2, hit=h) for h in (0, 10, 30, 60)]
    assert results[0] > results[1] > results[2] > results[3]


def test_none_static_falls_back_to_dynamic():
    """Missing static (pre-rescoring or old data) — use dynamic as-is."""
    assert compute_composite(None, 0.5, hit=20) == 0.5
