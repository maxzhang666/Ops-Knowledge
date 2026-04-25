"""Agentic RAG query planner (Plan 37 M1).

让 LLM 当 retrieval 调度者：判断当前 query 是否需要拆分为多个子查询
并行检索后再融合。典型场景：

  * "对比 PostgreSQL 与 MySQL 的索引机制" → 拆成
      [PostgreSQL 索引机制, MySQL 索引机制]
  * "我们的 RAG 系统流程是什么以及怎么调优" → 拆成
      [RAG 系统流程, RAG 系统调优方法]

非拆分场景（保持 single）：
  * 单一概念查询、错误码排查、术语定义

LLM 严格 JSON 输出：
    {"strategy": "single" | "decompose",
     "subqueries": ["...", "..."],
     "reason": "<10 字以内>"}

启发式短路：query 短（< 12 字符）、明显错误码、单标识符 → 直接 single，
省一次 LLM 调用。失败/解析异常一律 fallback single。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

import structlog

logger = structlog.get_logger(__name__)

ChatFn = Callable[[list[dict]], Awaitable[dict]]
Strategy = Literal["single", "decompose"]


@dataclass
class AgenticPlan:
    strategy: Strategy
    subqueries: list[str]   # decompose 时 ≥ 2；single 时为 [query]
    reason: str
    status: Literal["ok", "skipped", "fallback", "error"]


MAX_SUBQUERIES = 4
MIN_QUERY_LEN_FOR_PLANNING = 12  # 字符数


_PLAN_SYSTEM = (
    "你是 RAG 检索调度器。判断用户的查询是否需要拆分成多个子查询并行检索。"
    "拆分判定：含「与/和/以及/对比/差异/同时」等连接词、跨越多个独立主题、"
    "或问及多个相关但独立维度。\n\n"
    "严格返回 JSON：\n"
    '{"strategy": "single" | "decompose", '
    '"subqueries": ["子查询1", "子查询2", ...], '
    '"reason": "<10 字以内的简短理由>"}\n\n'
    "拆分约束：最多 4 条；每条独立可检索；不要扩写、不要解释、不要加引导词。"
    '若无需拆分，返回 {"strategy": "single", "subqueries": ["<原 query>"], "reason": "..."}。'
)


# ── 启发式短路 ────────────────────────────────────────────────────

_DECOMPOSE_HINTS = (
    "与", "和", "以及", "对比", "比较", "差异", "区别", "同时",
    " and ", " vs ", "compare", "difference between", "contrast",
)


def _looks_compound(query: str) -> bool:
    s = query.lower()
    return any(h in s for h in _DECOMPOSE_HINTS)


def _parse_response(text: str) -> dict:
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


# ── 主入口 ────────────────────────────────────────────────────────

async def plan(
    query: str,
    *,
    chat_fn: ChatFn | None = None,
) -> AgenticPlan:
    """规划检索策略。chat_fn=None 时一律 single（启发式 only 模式）。"""
    q = (query or "").strip()
    if not q:
        return AgenticPlan(strategy="single", subqueries=[], reason="empty", status="skipped")

    # 短查询/无连接词：启发式直接 single
    if len(q) < MIN_QUERY_LEN_FOR_PLANNING or not _looks_compound(q):
        return AgenticPlan(
            strategy="single", subqueries=[q],
            reason="standalone_heuristic", status="skipped",
        )

    if chat_fn is None:
        return AgenticPlan(
            strategy="single", subqueries=[q],
            reason="no_planner_llm", status="skipped",
        )

    messages = [
        {"role": "system", "content": _PLAN_SYSTEM},
        {"role": "user", "content": q},
    ]
    try:
        resp = await chat_fn(messages)
    except Exception as exc:
        logger.warning("agentic_planner_llm_failed", error=str(exc)[:200])
        return AgenticPlan(
            strategy="single", subqueries=[q],
            reason="llm_failed", status="error",
        )

    try:
        text = (resp.get("choices") or [])[0].get("message", {}).get("content", "")
    except Exception:
        text = ""
    parsed = _parse_response(text)

    strat = parsed.get("strategy") if isinstance(parsed, dict) else None
    raw_subs = parsed.get("subqueries") if isinstance(parsed, dict) else None
    reason = (parsed.get("reason") or "")[:80] if isinstance(parsed, dict) else "parse_failed"

    if strat == "decompose" and isinstance(raw_subs, list):
        subs = [str(s).strip() for s in raw_subs if isinstance(s, str)]
        subs = [s for s in subs if s][:MAX_SUBQUERIES]
        if len(subs) >= 2:
            logger.info("agentic_decomposed", original=q, subs=subs, reason=reason)
            return AgenticPlan(
                strategy="decompose", subqueries=subs,
                reason=reason or "llm_decomposed", status="ok",
            )

    # 任何不能解析为有效 decompose 的回应都退回 single
    return AgenticPlan(
        strategy="single", subqueries=[q],
        reason=reason or "fallback_single", status="fallback",
    )


def build_default_chat_fn():
    """系统默认 LLM 作为规划器；未配置 default 时返回 None。"""
    async def _chat(messages: list[dict]) -> dict:
        from app.core.database import async_session
        from app.model.service import ModelService
        from app.system.models import SystemSettings

        async with async_session() as db:
            row = await db.get(SystemSettings, 1)
            cfg = (row.settings or {}) if row else {}
            reg_id = cfg.get("default_llm_model_id")
            if not reg_id:
                raise RuntimeError("系统未配置默认 LLM，无法做 agentic planning")
            svc = ModelService(db)
            return await svc.chat_by_registry(
                uuid.UUID(str(reg_id)), messages, max_tokens=400,
            )

    return _chat
