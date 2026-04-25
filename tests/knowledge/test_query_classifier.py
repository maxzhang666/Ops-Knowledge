"""Plan 35 M5 — QueryClassifier rule coverage."""
from __future__ import annotations

import pytest

from app.knowledge.retrieval.query_classifier import (
    classify, recommend_strategy,
)


# ─── troubleshooting ──────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "用户登录失败 timeout",
    "Connection refused 报错",
    "Postgres connection reset by peer",
    "服务异常无法启动",
    "进程崩溃 traceback",
])
def test_troubleshooting_detected(q):
    r = classify(q)
    assert r.type == "troubleshooting"
    assert r.confidence >= 0.8


# ─── how_to ───────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "如何配置 SSL",
    "怎么安装 Docker",
    "How to deploy with kubernetes",
    "RAG 系统部署步骤",
    "How do I rotate API keys",
])
def test_how_to_detected(q):
    r = classify(q)
    assert r.type == "how_to"


# ─── definition ───────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "什么是 RAG",
    "RAG 是什么",
    "What is FAISS",
    "definition of HNSW",
    "meaning of embedding",
])
def test_definition_detected(q):
    r = classify(q)
    assert r.type == "definition"


# ─── concept ──────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "为什么 PostgreSQL 慢",
    "向量检索原理",
    "为啥需要 reranker",
    "Explain the architecture of LangChain",
    "Difference between BM25 and dense retrieval",
])
def test_concept_detected(q):
    r = classify(q)
    assert r.type == "concept"


# ─── lookup ───────────────────────────────────────────────────────

def test_lookup_short_keyword():
    assert classify("kafka").type == "lookup"
    assert classify("HNSW").type == "lookup"


def test_lookup_with_explicit_verb():
    assert classify("查询 PostgreSQL").type == "lookup"
    assert classify("search elasticsearch").type == "lookup"


def test_lookup_long_query_falls_through():
    # 长 query 不应当被 lookup 规则吃掉
    long_q = "A very long descriptive question about distributed systems and consensus algorithms"
    assert classify(long_q).type != "lookup"


# ─── other ────────────────────────────────────────────────────────

def test_unmatched_falls_back_to_other():
    r = classify("PostgreSQL 17 release notes")
    assert r.type == "other"
    assert r.confidence < 0.5


def test_empty_returns_other():
    r = classify("")
    assert r.type == "other"
    assert r.rationale == "empty"


# ─── recommend_strategy 表完整性 ───────────────────────────────────

@pytest.mark.parametrize("qt", [
    "troubleshooting", "concept", "how_to", "definition", "lookup", "other",
])
def test_recommend_strategy_covers_all_types(qt):
    s = recommend_strategy(qt)  # type: ignore[arg-type]
    assert 0.0 < s.bm25_weight <= 1.0
    assert 0.0 < s.vector_weight <= 1.0
    assert abs(s.bm25_weight + s.vector_weight - 1.0) < 1e-6
    assert s.top_k > 0


def test_troubleshooting_prefers_bm25():
    s = recommend_strategy("troubleshooting")
    assert s.bm25_weight > s.vector_weight


def test_concept_prefers_vector():
    s = recommend_strategy("concept")
    assert s.vector_weight > s.bm25_weight
