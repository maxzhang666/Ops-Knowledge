"""Plan 36 M3 — fusion algorithm tests (pure)."""
from __future__ import annotations

from app.knowledge.retrieval.fusion import (
    FusionConfig, _content_tokens, _jaccard, fuse_results, health_to_weight,
)
from app.knowledge.retrieval.searcher import SearchResult


def _hit(chunk_id: str, score: float, kb: str, content: str = "x") -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id, content=content, score=score,
        document_id="d", folder_id=None, level=0, title="t",
        source_kb_id=kb,
    )


# ─── health_to_weight ─────────────────────────────────────────────

def test_health_weight_neutral_when_none():
    assert health_to_weight(None) == 1.0


def test_health_weight_strong_kb_above_one():
    assert health_to_weight(80) > 1.0


def test_health_weight_weak_kb_below_one():
    assert health_to_weight(10) < 1.0


def test_health_weight_clamped():
    assert health_to_weight(150) == 1.5
    assert health_to_weight(-5) == 0.5


# ─── token / jaccard ──────────────────────────────────────────────

def test_content_tokens_handles_chinese():
    toks = _content_tokens("Postgres 数据库 索引")
    assert "postgres" in toks
    assert "数" in toks and "据" in toks


def test_jaccard_empty_sets_zero():
    assert _jaccard(set(), {"a"}) == 0.0


def test_jaccard_identical_one():
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0


# ─── source weighting ────────────────────────────────────────────

def test_weighting_promotes_strong_kb():
    # KB-A score 0.6 weight 1.5 → 0.9
    # KB-B score 0.7 weight 0.5 → 0.35
    a = _hit("a", 0.6, "kb-A")
    b = _hit("b", 0.7, "kb-B")
    out = fuse_results(
        [a, b],
        source_weights={"kb-A": 1.5, "kb-B": 0.5},
        config=FusionConfig(enable_cross_kb_dedup=False, enable_mmr=False),
        top_k=10,
    )
    assert out[0].chunk_id == "a"


def test_no_weights_keeps_score_order():
    a = _hit("a", 0.9, "kb-A")
    b = _hit("b", 0.5, "kb-B")
    out = fuse_results(
        [a, b],
        config=FusionConfig(enable_cross_kb_dedup=False, enable_mmr=False),
        top_k=10,
    )
    assert [r.chunk_id for r in out] == ["a", "b"]


# ─── cross-KB dedup ──────────────────────────────────────────────

def test_dedup_drops_lower_scoring_duplicate():
    a = _hit("a", 0.9, "kb-A")
    b = _hit("b", 0.6, "kb-B")
    c = _hit("c", 0.5, "kb-C")
    out = fuse_results(
        [a, b, c],
        dedup_pairs=[("a", "b")],
        config=FusionConfig(enable_source_weighting=False, enable_mmr=False),
        top_k=10,
    )
    ids = [r.chunk_id for r in out]
    assert "a" in ids
    assert "b" not in ids
    assert "c" in ids


def test_dedup_handles_unordered_pair():
    a = _hit("a", 0.9, "kb-A")
    b = _hit("b", 0.6, "kb-B")
    out = fuse_results(
        [a, b],
        dedup_pairs=[("b", "a")],
        config=FusionConfig(enable_source_weighting=False, enable_mmr=False),
        top_k=10,
    )
    assert len(out) == 1
    assert out[0].chunk_id == "a"


# ─── MMR diversity ───────────────────────────────────────────────

def test_mmr_prefers_diverse_over_redundant():
    # 三个候选：a 与 b 内容近似，c 完全不同；分数 a > b > c
    # 期望：a 入选种子；第二位 c（多样）而非 b
    a = _hit("a", 0.95, "kb-A", content="postgresql index tuning b-tree")
    b = _hit("b", 0.90, "kb-B", content="postgresql index tuning b-tree details")
    c = _hit("c", 0.60, "kb-C", content="kafka consumer group rebalance protocol")
    out = fuse_results(
        [a, b, c],
        config=FusionConfig(
            enable_source_weighting=False, enable_cross_kb_dedup=False,
            mmr_lambda=0.5,
        ),
        top_k=2,
    )
    assert out[0].chunk_id == "a"
    assert out[1].chunk_id == "c"


def test_top_k_truncates_after_fusion():
    hits = [_hit(f"x{i}", 0.5 + i * 0.01, "kb") for i in range(10)]
    out = fuse_results(hits, top_k=3)
    assert len(out) == 3


# ─── empty input ────────────────────────────────────────────────

def test_empty_returns_empty():
    assert fuse_results([], top_k=10) == []
