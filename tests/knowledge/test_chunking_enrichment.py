"""P24.M2 chunk enrichment — 纯解析 + 并发降级测试（mock LLM）。"""
from __future__ import annotations

import asyncio

import pytest

from app.knowledge.chunking.base import ChunkResult
from app.knowledge.chunking.enrichment import (
    _parse_response,
    enrich_chunks_async,
    EnrichmentOutput,
)


# ─── _parse_response 容错 ────────────────────────────────────────

def test_parse_strict_json():
    out = _parse_response('{"keywords": ["a", "b"], "questions": ["Q?"]}', True, True)
    assert out.keywords == ["a", "b"]
    assert out.questions == ["Q?"]


def test_parse_strips_code_fence():
    raw = "```json\n{\"keywords\": [\"x\"], \"questions\": []}\n```"
    out = _parse_response(raw, True, True)
    assert out.keywords == ["x"]


def test_parse_extracts_from_free_text():
    raw = "我帮你提取：\n{\"keywords\": [\"y\"]}\n完成。"
    out = _parse_response(raw, True, False)
    assert out.keywords == ["y"]


def test_parse_trims_punctuation():
    # 中文句尾标点会被剥掉，便于 index 使用
    out = _parse_response('{"keywords": ["关键词。", "带逗号，"]}', True, False)
    assert out.keywords == ["关键词", "带逗号"]


def test_parse_caps_counts():
    # keywords 最多 5，questions 最多 2
    raw = '{"keywords": ["1","2","3","4","5","6","7"], "questions": ["q1","q2","q3"]}'
    out = _parse_response(raw, True, True)
    assert len(out.keywords) == 5
    assert len(out.questions) == 2


def test_parse_handles_non_json():
    out = _parse_response("这不是 JSON", True, True)
    assert out.keywords == []
    assert out.questions == []


def test_parse_honors_want_flags():
    # 即使 LLM 吐出 questions，若 want_questions=False 仍返回 []
    raw = '{"keywords": ["a"], "questions": ["Q?"]}'
    out = _parse_response(raw, want_keywords=True, want_questions=False)
    assert out.keywords == ["a"]
    assert out.questions == []


# ─── enrich_chunks_async 并发 + 降级 ─────────────────────────────

def _mk_chunks(n: int) -> list[ChunkResult]:
    return [ChunkResult(content=f"片段 {i}", level=0, position=i) for i in range(n)]


@pytest.mark.asyncio
async def test_enrich_no_chunks_returns_empty():
    result = await enrich_chunks_async(
        [], chat_fn=lambda m: None,  # noqa: ARG005
        want_keywords=True, want_questions=False,
    )
    assert result == []


@pytest.mark.asyncio
async def test_enrich_skipped_when_both_flags_false():
    chunks = _mk_chunks(3)
    result = await enrich_chunks_async(
        chunks, chat_fn=lambda m: None,  # noqa: ARG005
        want_keywords=False, want_questions=False,
    )
    assert len(result) == 3
    assert all(r.keywords == [] and r.questions == [] for r in result)


@pytest.mark.asyncio
async def test_enrich_happy_path_with_mock_llm():
    async def chat_fn(messages):
        return {
            "choices": [
                {"message": {"content": '{"keywords": ["关键"], "questions": ["为什么?"]}'}}
            ],
        }

    chunks = _mk_chunks(3)
    result = await enrich_chunks_async(
        chunks, chat_fn=chat_fn,
        want_keywords=True, want_questions=True,
    )
    assert len(result) == 3
    for r in result:
        assert r.keywords == ["关键"]
        assert r.questions == ["为什么?"]


@pytest.mark.asyncio
async def test_enrich_failed_llm_does_not_raise():
    async def chat_fn(messages):
        raise RuntimeError("LLM boom")

    chunks = _mk_chunks(2)
    result = await enrich_chunks_async(
        chunks, chat_fn=chat_fn,
        want_keywords=True, want_questions=True,
    )
    # 全部降级到空，调用方照常入库
    assert [r.keywords for r in result] == [[], []]
    assert [r.questions for r in result] == [[], []]
