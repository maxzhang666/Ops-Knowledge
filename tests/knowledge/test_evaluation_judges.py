"""Plan 25 M2/M3 — judge prompts 解析 + mock LLM 行为测试。"""
from __future__ import annotations

import pytest

from app.knowledge.evaluation.judges import (
    JudgeResult,
    judge_answer_relevancy,
    judge_citation_accuracy,
    judge_context_precision,
    judge_faithfulness,
    judge_hallucination,
)


def _mk_chat_fn(content: str, raises: Exception | None = None):
    async def _chat(messages):
        if raises is not None:
            raise raises
        return {"choices": [{"message": {"content": content}}]}
    return _chat


# ─── Context Precision ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_precision_rank_weighted_avg():
    # 第一个 chunk 相关（1），第二个不相关（0）。rank-weighted precision =
    #   (1/1 + 0/2) / (1/1 + 1/2) = 1 / 1.5 = 0.6667
    chat_fn = _mk_chat_fn('{"scores": [1.0, 0.0], "rationale": "fine"}')
    r = await judge_context_precision(chat_fn, "查询", ["c1", "c2"])
    assert 0.66 < r.score < 0.67
    assert r.sample_count == 2


@pytest.mark.asyncio
async def test_context_precision_no_chunks():
    r = await judge_context_precision(_mk_chat_fn(""), "q", [])
    assert r.score == 0.0
    assert r.rationale == "no_chunks"


@pytest.mark.asyncio
async def test_context_precision_parse_failure_gives_neutral():
    r = await judge_context_precision(_mk_chat_fn("not json"), "q", ["c1"])
    assert r.score == 0.5
    assert r.rationale == "parse_failed"


# ─── Faithfulness ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_faithfulness_score_passthrough():
    r = await judge_faithfulness(
        _mk_chat_fn('{"score": 0.8, "unsupported": [], "rationale": "ok"}'),
        "answer", "context",
    )
    assert r.score == 0.8


@pytest.mark.asyncio
async def test_faithfulness_clamps_out_of_range():
    r = await judge_faithfulness(
        _mk_chat_fn('{"score": 1.5, "rationale": ""}'),
        "a", "c",
    )
    assert r.score == 1.0


# ─── Answer Relevancy ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_relevancy_missing_input():
    r = await judge_answer_relevancy(_mk_chat_fn(""), "", "")
    assert r.score == 0.0
    assert r.rationale == "missing_input"


@pytest.mark.asyncio
async def test_answer_relevancy_llm_exception_gives_neutral():
    r = await judge_answer_relevancy(
        _mk_chat_fn("", raises=RuntimeError("boom")),
        "q", "a",
    )
    assert r.score == 0.5


# ─── Hallucination ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hallucination_zero_hallucinated_is_100():
    r = await judge_hallucination(
        _mk_chat_fn('{"hallucinated_claims": 0, "total_claims": 5, "rationale": "clean"}'),
        "a", "c",
    )
    assert r.score == 1.0
    assert r.sample_count == 5


@pytest.mark.asyncio
async def test_hallucination_partial():
    r = await judge_hallucination(
        _mk_chat_fn('{"hallucinated_claims": 2, "total_claims": 5}'),
        "a", "c",
    )
    # 1 - 2/5 = 0.6
    assert abs(r.score - 0.6) < 1e-6


@pytest.mark.asyncio
async def test_hallucination_no_claims_is_neutral():
    r = await judge_hallucination(
        _mk_chat_fn('{"hallucinated_claims": 0, "total_claims": 0}'),
        "a", "c",
    )
    assert r.score == 0.5
    assert r.rationale == "no_claims_found"


# ─── Citation Accuracy ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_citation_accuracy_averages_scores():
    r = await judge_citation_accuracy(
        _mk_chat_fn('{"scores": [1.0, 0.5, 0.0]}'),
        "answer",
        [{"index": i, "title": "t", "chunk_text": "x"} for i in (1, 2, 3)],
    )
    assert abs(r.score - 0.5) < 1e-6
    assert r.sample_count == 3


@pytest.mark.asyncio
async def test_citation_accuracy_no_citations():
    r = await judge_citation_accuracy(_mk_chat_fn(""), "a", [])
    assert r.score == 0.0
    assert r.rationale == "no_citations"
