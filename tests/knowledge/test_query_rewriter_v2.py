"""Plan 30 M4 — query_rewriter_v2 启发式与解析层测试（mock LLM）。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.knowledge.retrieval.query_rewriter import (
    RewriteResult,
    _has_followup_hint,
    _parse_response,
    rewrite_query_v2,
)


# ─── _has_followup_hint ───────────────────────────────────────────

def test_followup_hint_chinese_pronoun():
    assert _has_followup_hint("它的内存大小是多少？")
    assert _has_followup_hint("这个怎么用？")
    assert _has_followup_hint("上面那个继续讲")


def test_followup_hint_standalone_query_returns_false():
    assert not _has_followup_hint("OpenAPI 3.0 协议是什么？")
    assert not _has_followup_hint("PostgreSQL 主键索引设计")


def test_followup_hint_english_pronouns():
    assert _has_followup_hint("its memory limit?")
    assert _has_followup_hint("what about that one?")


def test_followup_hint_empty():
    assert not _has_followup_hint("")
    assert not _has_followup_hint("   ")


# ─── _parse_response ──────────────────────────────────────────────

def test_parse_response_strict_json():
    parsed = _parse_response('{"needs_rewrite": true, "rewritten": "查询", "reason": "代词"}')
    assert parsed["needs_rewrite"] is True
    assert parsed["rewritten"] == "查询"


def test_parse_response_code_fence():
    raw = '```json\n{"needs_rewrite": false, "rewritten": "x"}\n```'
    parsed = _parse_response(raw)
    assert parsed["needs_rewrite"] is False


def test_parse_response_freetext_extract():
    raw = "好的：{\"needs_rewrite\": true, \"rewritten\": \"PostgreSQL 内存限制\"}"
    parsed = _parse_response(raw)
    assert parsed["rewritten"] == "PostgreSQL 内存限制"


def test_parse_response_invalid_returns_empty():
    assert _parse_response("not json") == {}


# ─── rewrite_query_v2 短路逻辑 ────────────────────────────────────

@pytest.mark.asyncio
async def test_v2_empty_query_skipped():
    r = await rewrite_query_v2("   ", [{"role": "user", "content": "x"}])
    assert r.status == "skipped"
    assert r.reason == "empty"


@pytest.mark.asyncio
async def test_v2_no_history_skipped():
    r = await rewrite_query_v2("具体说说", [])
    assert r.status == "skipped"
    assert r.reason == "no_history"


@pytest.mark.asyncio
async def test_v2_long_standalone_query_skipped_without_llm():
    # 长查询且无续接词 → 启发式判定独立，跳过 LLM
    long_q = "PostgreSQL 数据库主键索引应该如何选择 hash 还是 b-tree？"
    r = await rewrite_query_v2(
        long_q,
        [{"role": "user", "content": "之前问过别的"}],
    )
    assert r.status == "skipped"
    assert "standalone" in r.reason


@pytest.mark.asyncio
async def test_v2_no_model_config_skipped():
    # 即使含续接词，没配 model 时直接 skip 不报错
    r = await rewrite_query_v2(
        "它的限制是？",
        [{"role": "user", "content": "讲讲 Redis"}],
    )
    assert r.status == "skipped"
    assert r.reason == "no_model_config"


@pytest.mark.asyncio
async def test_v2_llm_says_no_rewrite_returns_original():
    async def fake_chat(provider_id, model_name, messages, **kw):
        return {"choices": [{"message": {"content": '{"needs_rewrite": false, "rewritten": "x", "reason": "self-contained"}'}}]}

    with patch("app.knowledge.retrieval.query_rewriter.ModelService") as MS:
        MS.return_value.chat = fake_chat
        r = await rewrite_query_v2(
            "它什么时候发布？",
            [{"role": "user", "content": "PostgreSQL 17"}],
            provider_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
            model_name="gpt-4o-mini",
        )
    assert r.status == "skipped"
    assert r.query_used == "它什么时候发布？"


@pytest.mark.asyncio
async def test_v2_llm_rewrites_returns_new_query():
    async def fake_chat(provider_id, model_name, messages, **kw):
        return {"choices": [{"message": {"content": '{"needs_rewrite": true, "rewritten": "PostgreSQL 17 发布日期", "reason": "代词"}'}}]}

    with patch("app.knowledge.retrieval.query_rewriter.ModelService") as MS:
        MS.return_value.chat = fake_chat
        r = await rewrite_query_v2(
            "它什么时候发布？",
            [{"role": "user", "content": "PostgreSQL 17"}],
            provider_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
            model_name="gpt-4o-mini",
        )
    assert r.status == "ok"
    assert r.needs_rewrite
    assert r.query_used == "PostgreSQL 17 发布日期"


@pytest.mark.asyncio
async def test_v2_llm_failure_falls_back():
    async def boom(*args, **kw):
        raise RuntimeError("LLM down")

    with patch("app.knowledge.retrieval.query_rewriter.ModelService") as MS:
        MS.return_value.chat = boom
        r = await rewrite_query_v2(
            "它怎么样？",
            [{"role": "user", "content": "Redis"}],
            provider_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
            model_name="gpt-4o-mini",
        )
    assert r.status == "error"
    assert r.query_used == "它怎么样？"


@pytest.mark.asyncio
async def test_v2_parse_failure_falls_back():
    async def fake_chat(provider_id, model_name, messages, **kw):
        return {"choices": [{"message": {"content": "not json at all"}}]}

    with patch("app.knowledge.retrieval.query_rewriter.ModelService") as MS:
        MS.return_value.chat = fake_chat
        r = await rewrite_query_v2(
            "它的价格？",
            [{"role": "user", "content": "GPT-4"}],
            provider_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
            model_name="gpt-4o-mini",
        )
    # 解析失败时应回 skipped + 原 query
    assert r.status == "skipped"
    assert r.query_used == "它的价格？"


def test_rewrite_result_dataclass():
    r = RewriteResult(
        query_used="x", needs_rewrite=True, reason="r", status="ok",
    )
    assert r.query_used == "x"
    assert r.status == "ok"
