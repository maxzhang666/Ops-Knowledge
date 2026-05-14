"""Spec 25 Plan A — 纯逻辑单测：canonicalize / tag_filter expr / embed text / chunk_tags 派生。

避免触碰真 DB / Milvus / Redis。
"""
from __future__ import annotations

from app.knowledge.chunk_service import _compute_chunk_tags_from_unit
from app.knowledge.embedding.service import _build_embedding_text
from app.knowledge.retrieval.searcher import _build_tag_filter_expr
from app.knowledge.tagging.normalizer import canonicalize_input


# ── canonicalize_input ───────────────────────────────────────────


def test_canonicalize_trims_and_lowercases():
    assert canonicalize_input("  Hello  ") == "hello"


def test_canonicalize_replaces_fullwidth_space():
    assert canonicalize_input("退　款") == "退 款"


def test_canonicalize_empty_returns_empty():
    assert canonicalize_input("") == ""
    assert canonicalize_input("   　   ") == ""


# ── _build_tag_filter_expr ───────────────────────────────────────


def test_filter_expr_any_of():
    assert _build_tag_filter_expr({"any_of": ["退款"]}) == \
        'array_contains_any(chunk_tags, ["退款"])'


def test_filter_expr_all_of():
    assert _build_tag_filter_expr({"all_of": ["退款", "售后"]}) == \
        'array_contains_all(chunk_tags, ["退款", "售后"])'


def test_filter_expr_not():
    assert _build_tag_filter_expr({"not": ["营销"]}) == \
        'not array_contains_any(chunk_tags, ["营销"])'


def test_filter_expr_combined_anded():
    """三种语义 AND 串联。"""
    expr = _build_tag_filter_expr({"any_of": ["a"], "not": ["b"]})
    assert "and" in expr
    assert 'array_contains_any(chunk_tags, ["a"])' in expr
    assert 'not array_contains_any(chunk_tags, ["b"])' in expr


def test_filter_expr_empty_returns_none():
    assert _build_tag_filter_expr(None) is None
    assert _build_tag_filter_expr({}) is None
    assert _build_tag_filter_expr({"any_of": []}) is None


def test_filter_expr_strips_empty_strings():
    """空字符串元素被忽略。"""
    expr = _build_tag_filter_expr({"any_of": ["", "退款", None]})
    # None 也算 falsy 应被过滤
    assert "退款" in expr
    assert '""' not in expr


# ── _build_embedding_text ────────────────────────────────────────


def test_embed_text_long_no_signals_returns_content():
    """长 chunk 无 tags 无 heading → 原 content（M6.6 默认）。"""
    long_content = "a" * 300
    assert _build_embedding_text({"content": long_content}) == long_content


def test_embed_text_with_tags_uses_structured_prefix():
    """有 tags 即触发结构化前缀（不论长短）。"""
    result = _build_embedding_text({
        "content": "短内容", "chunk_tags": ["退款", "售后"],
    })
    assert result.startswith("[TAGS] ")
    assert "退款, 售后" in result
    assert "[CONTENT] 短内容" in result


def test_embed_text_with_heading_short_chunk():
    """短 chunk + heading → [TITLE] + [CONTENT]，行为对齐 M6.7。"""
    result = _build_embedding_text({
        "content": "短内容",
        "metadata": {"heading": "# 退款流程"},
    })
    assert "[TITLE] # 退款流程" in result
    assert "[CONTENT] 短内容" in result


def test_embed_text_caps_tag_count():
    """超过 _MAX_TAGS_IN_PREFIX(=10) 的 tags 被截断。"""
    tags = [f"t{i}" for i in range(20)]
    result = _build_embedding_text({"content": "x", "chunk_tags": tags})
    # 只前 10 个出现
    for i in range(10):
        assert f"t{i}" in result
    for i in range(15, 20):
        assert f"t{i}" not in result


# ── _compute_chunk_tags_from_unit ────────────────────────────────


def test_compute_chunk_tags_union_user_and_auto():
    class _E:
        tags = ["退款", "售后"]
        auto_tags = [
            {"tag": "客服", "confidence": 0.9},
            {"tag": "退款", "confidence": 0.8},  # 重复，被去重
        ]
    out = _compute_chunk_tags_from_unit(_E())
    assert out == ["退款", "售后", "客服"]


def test_compute_chunk_tags_document_returns_none():
    """Document 类无 tags 字段 → None。"""
    class _D:
        pass
    assert _compute_chunk_tags_from_unit(_D()) is None


def test_compute_chunk_tags_empty_returns_none():
    class _E:
        tags = []
        auto_tags = []
    assert _compute_chunk_tags_from_unit(_E()) is None


def test_compute_chunk_tags_skips_invalid_auto():
    class _E:
        tags = ["a"]
        auto_tags = [
            {"tag": "b", "confidence": 0.5},
            {"confidence": 0.9},  # 无 tag 字段
            None,                  # 完全无效
            "raw_str",             # 不符合期望 shape
        ]
    out = _compute_chunk_tags_from_unit(_E())
    assert out == ["a", "b"]
