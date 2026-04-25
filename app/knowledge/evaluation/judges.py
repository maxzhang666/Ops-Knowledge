"""LLM-as-Judge prompts + 解析（Plan 25 M2/M3）.

每个指标独立一个判官函数：输入纯数据（无 DB / HTTP 依赖），返回
``(score_0_1, rationale)``。这样可直接 mock chat_fn 做单元测试。

所有指标都强制 LLM 返回严格 JSON，解析层带三重容错（strict JSON →
代码块剥离 → 正则抽 JSON），失败返回默认 0.5 + "parse_failed" 作为
中性分，避免一次判官异常让 message 的整体评估永远缺失。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)

ChatFn = Callable[[list[dict]], Awaitable[dict]]


@dataclass
class JudgeResult:
    score: float  # 0..1
    rationale: str
    sample_count: int | None = None


# ─── 通用响应解析 ────────────────────────────────────────────────

def _extract_text(resp: dict) -> str:
    choices = (resp or {}).get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def _parse_json(text: str) -> dict:
    """三步容错解析：严格 → 剥代码块 → 正则抽。"""
    body = (text or "").strip()
    try:
        return json.loads(body)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m2 = re.search(r"\{[\s\S]*\}", body)
    if m2:
        try:
            return json.loads(m2.group(0))
        except Exception:
            pass
    return {}


def _clamp01(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


async def _judge_call(
    chat_fn: ChatFn,
    system_prompt: str,
    user_prompt: str,
) -> dict:
    try:
        resp = await chat_fn(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as exc:
        logger.debug("judge_llm_failed", error=str(exc)[:200])
        return {}
    return _parse_json(_extract_text(resp))


# ─── Layer 3: Context Precision ───────────────────────────────────

_CP_SYSTEM = (
    "你是检索质量评估员。判断每个候选片段对用户查询的相关性（0-1 之间小数，"
    "1 完全相关，0 完全无关）。严格返回 JSON：\n"
    '{"scores": [<每个片段一个分>], "rationale": "<简短说明>"}'
)


def _build_cp_prompt(query: str, chunks: list[str]) -> str:
    joined = "\n\n".join(
        f"[片段 {i+1}]\n{c.strip()[:1200]}" for i, c in enumerate(chunks)
    )
    return (
        f"查询：{query}\n\n以下是检索返回的片段，请分别打分：\n\n{joined}"
    )


async def judge_context_precision(
    chat_fn: ChatFn, query: str, chunks: list[str],
) -> JudgeResult:
    if not query or not chunks:
        return JudgeResult(score=0.0, rationale="no_chunks")
    parsed = await _judge_call(chat_fn, _CP_SYSTEM, _build_cp_prompt(query, chunks))
    raw_scores = parsed.get("scores") if isinstance(parsed, dict) else None
    if not isinstance(raw_scores, list) or not raw_scores:
        return JudgeResult(score=0.5, rationale="parse_failed")
    scores = [_clamp01(s) for s in raw_scores[: len(chunks)]]
    if not scores:
        return JudgeResult(score=0.5, rationale="parse_failed")
    # Precision at K — 高分 chunk 占比 + 排序加权（rank-weighted precision）
    n = len(scores)
    weighted = sum(s / (i + 1) for i, s in enumerate(scores))
    normalizer = sum(1.0 / (i + 1) for i in range(n))
    score = weighted / normalizer if normalizer > 0 else 0.0
    return JudgeResult(
        score=score,
        rationale=(parsed.get("rationale") or "")[:500],
        sample_count=n,
    )


# ─── Layer 4: Faithfulness ────────────────────────────────────────

_FAITH_SYSTEM = (
    "你是事实一致性评估员。判断回答中的每个核心断言是否被所给上下文支持。"
    "严格返回 JSON：\n"
    '{"score": <0-1 小数，1 完全一致>, "unsupported": ["<未被支持的断言>"], '
    '"rationale": "<简短说明>"}'
)


def _build_faith_prompt(answer: str, context: str) -> str:
    return (
        f"【上下文】\n{context.strip()[:6000]}\n\n"
        f"【回答】\n{answer.strip()[:3000]}\n\n"
        "请评分并列出未被支持的断言（如有）。"
    )


async def judge_faithfulness(
    chat_fn: ChatFn, answer: str, context: str,
) -> JudgeResult:
    if not answer or not context:
        return JudgeResult(score=0.0, rationale="missing_input")
    parsed = await _judge_call(chat_fn, _FAITH_SYSTEM, _build_faith_prompt(answer, context))
    if not isinstance(parsed, dict) or "score" not in parsed:
        return JudgeResult(score=0.5, rationale="parse_failed")
    return JudgeResult(
        score=_clamp01(parsed.get("score")),
        rationale=(parsed.get("rationale") or "")[:500],
    )


# ─── Layer 4: Answer Relevancy ────────────────────────────────────

_REL_SYSTEM = (
    "你是回答切题度评估员。评估回答是否紧扣用户问题，无跑题、无敷衍。"
    "严格返回 JSON：\n"
    '{"score": <0-1>, "rationale": "<简短>"}'
)


def _build_rel_prompt(query: str, answer: str) -> str:
    return f"问题：{query}\n\n回答：{answer.strip()[:3000]}\n\n请评分。"


async def judge_answer_relevancy(
    chat_fn: ChatFn, query: str, answer: str,
) -> JudgeResult:
    if not query or not answer:
        return JudgeResult(score=0.0, rationale="missing_input")
    parsed = await _judge_call(chat_fn, _REL_SYSTEM, _build_rel_prompt(query, answer))
    if not isinstance(parsed, dict) or "score" not in parsed:
        return JudgeResult(score=0.5, rationale="parse_failed")
    return JudgeResult(
        score=_clamp01(parsed.get("score")),
        rationale=(parsed.get("rationale") or "")[:500],
    )


# ─── Layer 4: Hallucination Detection ─────────────────────────────

_HAL_SYSTEM = (
    "你是幻觉检测员。统计回答中包含的、未出现在上下文中的虚构事实数量。"
    '严格 JSON：{"hallucinated_claims": <int>, "total_claims": <int>, '
    '"examples": ["<虚构断言示例>"], "rationale": "<简短>"}'
)


def _build_hal_prompt(answer: str, context: str) -> str:
    return (
        f"【上下文】\n{context.strip()[:6000]}\n\n"
        f"【回答】\n{answer.strip()[:3000]}"
    )


async def judge_hallucination(
    chat_fn: ChatFn, answer: str, context: str,
) -> JudgeResult:
    """返回 score = 1 - (hallucinated / max(total_claims, 1))。"""
    if not answer or not context:
        return JudgeResult(score=0.0, rationale="missing_input")
    parsed = await _judge_call(chat_fn, _HAL_SYSTEM, _build_hal_prompt(answer, context))
    if not isinstance(parsed, dict):
        return JudgeResult(score=0.5, rationale="parse_failed")
    try:
        hc = int(parsed.get("hallucinated_claims") or 0)
        tc = int(parsed.get("total_claims") or 0)
    except (TypeError, ValueError):
        return JudgeResult(score=0.5, rationale="parse_failed")
    if tc <= 0:
        # 无断言 → 没法判定幻觉，给中性
        return JudgeResult(score=0.5, rationale="no_claims_found")
    score = max(0.0, 1.0 - (hc / tc))
    return JudgeResult(
        score=score,
        rationale=(parsed.get("rationale") or "")[:500],
        sample_count=tc,
    )


# ─── Layer 4: Citation Accuracy ───────────────────────────────────

_CITE_SYSTEM = (
    "你是引用校验员。逐一判断每条 citation 指向的源片段是否真实支持"
    "引用处的陈述。严格 JSON：\n"
    '{"scores": [<每个 citation 一个 0-1>], "rationale": "<简短>"}'
)


def _build_cite_prompt(answer: str, citations: list[dict]) -> str:
    """citations 形如 [{"index": 1, "title": "...", "chunk_text": "..."}]。"""
    lines = [f"【回答】\n{answer.strip()[:3000]}", "", "【引用】"]
    for c in citations:
        idx = c.get("index")
        title = c.get("title", "")
        text = (c.get("chunk_text") or "").strip()[:800]
        lines.append(f"[{idx}] {title}：\n{text}")
    return "\n".join(lines)


async def judge_citation_accuracy(
    chat_fn: ChatFn, answer: str, citations: list[dict],
) -> JudgeResult:
    if not answer or not citations:
        return JudgeResult(score=0.0, rationale="no_citations")
    parsed = await _judge_call(chat_fn, _CITE_SYSTEM, _build_cite_prompt(answer, citations))
    raw_scores = parsed.get("scores") if isinstance(parsed, dict) else None
    if not isinstance(raw_scores, list) or not raw_scores:
        return JudgeResult(score=0.5, rationale="parse_failed")
    scores = [_clamp01(s) for s in raw_scores[: len(citations)]]
    if not scores:
        return JudgeResult(score=0.5, rationale="parse_failed")
    avg = sum(scores) / len(scores)
    return JudgeResult(
        score=avg,
        rationale=(parsed.get("rationale") or "")[:500],
        sample_count=len(scores),
    )
