"""Plan 37 M4 — agentic_planner tests (mock LLM)."""
from __future__ import annotations

import pytest

from app.knowledge.retrieval.agentic_planner import (
    MAX_SUBQUERIES, MIN_QUERY_LEN_FOR_PLANNING,
    AgenticPlan, _looks_compound, _parse_response, plan,
)


def _mk_chat(content: str):
    async def _chat(messages):
        return {"choices": [{"message": {"content": content}}]}
    return _chat


# ─── _looks_compound ──────────────────────────────────────────────

def test_looks_compound_chinese_connectors():
    assert _looks_compound("对比 PostgreSQL 与 MySQL 索引")
    assert _looks_compound("性能差异以及配置")


def test_looks_compound_english_connectors():
    assert _looks_compound("PostgreSQL vs MySQL")
    assert _looks_compound("compare A and B")


def test_looks_compound_negative():
    assert not _looks_compound("什么是 RAG")
    assert not _looks_compound("how to install docker")


# ─── _parse_response ──────────────────────────────────────────────

def test_parse_strict_json():
    p = _parse_response('{"strategy": "decompose", "subqueries": ["a","b"]}')
    assert p["strategy"] == "decompose"


def test_parse_code_fence():
    p = _parse_response('```json\n{"strategy": "single", "subqueries": ["x"]}\n```')
    assert p["strategy"] == "single"


def test_parse_garbage_returns_empty():
    assert _parse_response("nope") == {}


# ─── plan() short-circuits ────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_query_skips_to_single():
    r = await plan("", chat_fn=_mk_chat("{}"))
    assert r.strategy == "single"
    assert r.reason == "empty"


@pytest.mark.asyncio
async def test_short_query_short_circuits():
    short = "x" * (MIN_QUERY_LEN_FOR_PLANNING - 1)
    r = await plan(short, chat_fn=_mk_chat("{}"))
    assert r.strategy == "single"
    assert r.status == "skipped"


@pytest.mark.asyncio
async def test_long_query_without_connectors_skips_llm():
    # 超过最小长度但无连接词 → 启发式不调 LLM
    called = {"n": 0}
    async def boom(_m):
        called["n"] += 1
        return {"choices": [{"message": {"content": "{}"}}]}
    r = await plan("详细说明 PostgreSQL 索引调优", chat_fn=boom)
    assert r.strategy == "single"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_no_chat_fn_returns_single():
    r = await plan("对比 PostgreSQL 与 MySQL")
    assert r.strategy == "single"
    assert r.reason == "no_planner_llm"


# ─── plan() with LLM ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_decompose_happy_path():
    chat = _mk_chat(
        '{"strategy":"decompose","subqueries":["PostgreSQL 索引","MySQL 索引"],"reason":"对比"}'
    )
    r = await plan("对比 PostgreSQL 与 MySQL 索引机制", chat_fn=chat)
    assert r.strategy == "decompose"
    assert r.subqueries == ["PostgreSQL 索引", "MySQL 索引"]
    assert r.status == "ok"


@pytest.mark.asyncio
async def test_llm_decompose_caps_at_max():
    subs = [f"q{i}" for i in range(10)]
    chat = _mk_chat(
        '{"strategy":"decompose","subqueries":' + str(subs).replace("'", '"') + "}"
    )
    r = await plan("跨多主题对比 与 分析", chat_fn=chat)
    assert len(r.subqueries) <= MAX_SUBQUERIES


@pytest.mark.asyncio
async def test_llm_decompose_with_one_sub_falls_back_to_single():
    chat = _mk_chat('{"strategy":"decompose","subqueries":["only one"]}')
    r = await plan("对比 PostgreSQL 与 MySQL 的索引", chat_fn=chat)
    assert r.strategy == "single"
    assert r.status == "fallback"


@pytest.mark.asyncio
async def test_llm_returns_single_passes_through():
    chat = _mk_chat('{"strategy":"single","subqueries":["..."],"reason":"self-contained"}')
    r = await plan("对比 PostgreSQL 与 MySQL 的差异 的情况", chat_fn=chat)
    assert r.strategy == "single"


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_single():
    async def boom(_m):
        raise RuntimeError("LLM boom")
    r = await plan("对比 PostgreSQL 与 MySQL 的差异", chat_fn=boom)
    assert r.strategy == "single"
    assert r.status == "error"


@pytest.mark.asyncio
async def test_llm_garbage_response_falls_back():
    chat = _mk_chat("not json at all")
    r = await plan("对比 PostgreSQL 与 MySQL 的差异", chat_fn=chat)
    assert r.strategy == "single"
    assert r.status == "fallback"


def test_dataclass_smoke():
    p = AgenticPlan(strategy="single", subqueries=["x"], reason="r", status="ok")
    assert p.strategy == "single"
