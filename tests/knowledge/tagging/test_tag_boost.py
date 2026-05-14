"""Spec 25 Plan C — L4 rerank tag boost 纯逻辑单测。

mock canonical embeddings + chunk_tags + query_vector，验证：
- relevant canonicals 取 top-K 且过滤 cosine<=0
- 命中数 * boost_weight 正确加到 fused score
- feature flag：weight<=0 或 empty embeddings 时 noop
- chunk_tags 缺失 / 非 list 时跳过
"""
from __future__ import annotations

import pytest

from app.knowledge.retrieval.searcher import (
    _apply_tag_boost,
    _cosine_sim,
    _select_relevant_canonicals,
)


# ── _cosine_sim ──────────────────────────────────────────────────


def test_cosine_identical():
    assert _cosine_sim([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert _cosine_sim([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_zero_vector():
    assert _cosine_sim([0, 0], [1, 1]) == 0.0
    assert _cosine_sim([1, 1], [0, 0]) == 0.0


def test_cosine_mismatched_dim():
    assert _cosine_sim([1, 0], [1, 0, 0]) == 0.0


def test_cosine_none_safe():
    assert _cosine_sim(None, [1, 0]) == 0.0
    assert _cosine_sim([1, 0], None) == 0.0


# ── _select_relevant_canonicals ──────────────────────────────────


def test_select_relevant_takes_top_k_with_positive_sim():
    q = [1.0, 0.0]
    embeddings = {
        "退款": [1.0, 0.0],    # cosine 1.0
        "售后": [0.9, 0.1],    # ≈0.995
        "营销": [0.0, 1.0],    # 0.0 — 过滤
        "广告": [-1.0, 0.0],   # <0 — 过滤
        "客服": [0.5, 0.5],    # ≈0.707
    }
    relevant = _select_relevant_canonicals(q, embeddings, top_k=3)
    # top 3 positive: 退款 / 售后 / 客服
    assert relevant == {"退款", "售后", "客服"}


def test_select_relevant_empty_inputs():
    assert _select_relevant_canonicals([1, 0], {}) == set()
    assert _select_relevant_canonicals([], {"a": [1, 0]}) == set()


def test_select_relevant_top_k_cap():
    """K 小于实际正分项数 → 截前 K。"""
    q = [1.0, 0.0]
    emb = {f"t{i}": [1.0 - i * 0.01, 0.01] for i in range(10)}
    relevant = _select_relevant_canonicals(q, emb, top_k=3)
    assert len(relevant) == 3
    # 最高分 t0/t1/t2
    assert relevant == {"t0", "t1", "t2"}


# ── _apply_tag_boost ─────────────────────────────────────────────


def _row(fused: float, chunk_tags: list[str] | None) -> dict:
    return {
        "fused": fused,
        "entity": {"chunk_tags": chunk_tags} if chunk_tags is not None else {},
    }


def test_apply_boost_basic_hit():
    """chunk_tags ∩ relevant 命中数 * weight 加到 fused。"""
    merged = {"c1": _row(0.5, ["退款", "售后"])}
    canon_emb = {
        "退款": [1.0, 0.0],
        "售后": [0.9, 0.1],
        "营销": [0.0, 1.0],
    }
    _apply_tag_boost(merged, [1.0, 0.0], canon_emb, boost_weight=0.05)
    # 退款+售后 都在 top-K → hit_count=2 → boost=0.1
    assert merged["c1"]["fused"] == pytest.approx(0.6)
    assert merged["c1"]["tag_boost"] == pytest.approx(0.1)


def test_apply_boost_noop_when_weight_zero():
    """boost_weight<=0 时直接 noop（feature flag）。"""
    merged = {"c1": _row(0.5, ["退款"])}
    _apply_tag_boost(merged, [1, 0], {"退款": [1, 0]}, boost_weight=0.0)
    assert merged["c1"]["fused"] == 0.5
    assert "tag_boost" not in merged["c1"]


def test_apply_boost_noop_when_no_canonicals():
    merged = {"c1": _row(0.5, ["退款"])}
    _apply_tag_boost(merged, [1, 0], None, boost_weight=0.05)
    assert merged["c1"]["fused"] == 0.5
    _apply_tag_boost(merged, [1, 0], {}, boost_weight=0.05)
    assert merged["c1"]["fused"] == 0.5


def test_apply_boost_no_chunk_tags_skip():
    """chunk 没有 chunk_tags → 跳过，不爆。"""
    merged = {
        "c1": _row(0.5, None),    # 无 entity.chunk_tags
        "c2": _row(0.3, []),      # 空列表
    }
    _apply_tag_boost(merged, [1, 0], {"退款": [1, 0]}, boost_weight=0.05)
    assert merged["c1"]["fused"] == 0.5
    assert merged["c2"]["fused"] == 0.3


def test_apply_boost_only_relevant_count():
    """chunk_tags 中只有 relevant 的命中算分；irrelevant 不计。"""
    merged = {"c1": _row(0.5, ["退款", "营销", "未上 prompt 的词"])}
    canon_emb = {
        "退款": [1.0, 0.0],   # relevant
        "营销": [0.0, 1.0],   # 不 relevant（cosine 0，被 filter）
    }
    _apply_tag_boost(merged, [1.0, 0.0], canon_emb, boost_weight=0.1)
    # 仅退款 hit → boost 0.1
    assert merged["c1"]["fused"] == pytest.approx(0.6)
    assert merged["c1"]["tag_boost"] == pytest.approx(0.1)


def test_apply_boost_non_list_chunk_tags_skipped():
    """chunk_tags 字段被错误设成非 list → 跳过。"""
    merged = {"c1": {"fused": 0.5, "entity": {"chunk_tags": "退款"}}}
    _apply_tag_boost(merged, [1, 0], {"退款": [1, 0]}, boost_weight=0.05)
    assert merged["c1"]["fused"] == 0.5


def test_apply_boost_multiple_chunks_independent():
    """多 chunk 各自计算 boost；不互相影响。"""
    merged = {
        "c1": _row(0.5, ["退款", "售后"]),
        "c2": _row(0.4, ["退款"]),
        "c3": _row(0.3, ["不相关词"]),
    }
    canon_emb = {"退款": [1.0, 0.0], "售后": [0.9, 0.1]}
    _apply_tag_boost(merged, [1.0, 0.0], canon_emb, boost_weight=0.05)
    assert merged["c1"]["fused"] == pytest.approx(0.6)   # 2*0.05
    assert merged["c2"]["fused"] == pytest.approx(0.45)  # 1*0.05
    assert merged["c3"]["fused"] == 0.3  # chunk_tags 不在 relevant 中
