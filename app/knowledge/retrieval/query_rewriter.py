"""Conversational Query Rewriter (Plan 30 v2).

把对话历史 + 当前问题 → 独立可检索查询。改进点：

1. **跳过判定** —— 不是每次提问都需要改写。例如新话题第一句问句无需改写。
   通过 LLM 分类 (`needs_rewrite`) + 关键词启发式（"它/这个/上面/上述/继续"
   等指代/续接词）双道滤网；二者均否决则原样返回，省一次 LLM 调用。

2. **结构化输出** —— LLM 严格 JSON：
       {"needs_rewrite": bool, "rewritten": str, "reason": str}
   三层解析容错；解析失败回到原 query。

3. **registry 支持** —— 同时接受 ``registry_id`` 与传统 ``provider_id +
   model_name``；上游可逐步切到 registry。

4. **memory_summary 注入** —— 调用方可把 conversation.memory_summary 作为
   一条 system 风格 prefix 注入历史，扩大长程上下文。

5. **失败降级** —— 任何异常返回原 query；调用方拿到的 ``RewriteResult``
   带 ``status`` 让 telemetry 可观测。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Literal

import structlog

from app.core.database import async_session
from app.model.service import ModelService

logger = structlog.get_logger(__name__)


REWRITE_SYSTEM = (
    "你是对话检索的查询改写器。给定对话历史 + 用户最新问题，判断是否需要"
    "结合上下文将问题改写为独立的可检索查询。需要改写的典型场景："
    "包含指代词（它/这个/上述/前面）、省略主语、跟进追问。\n\n"
    "严格返回 JSON：\n"
    '{"needs_rewrite": <true|false>, "rewritten": "<改写后的独立查询，'
    '或与原问题相同>", "reason": "<简短理由，10 字以内>"}\n\n'
    "改写规则：保留原问题的核心意图，将代词替换为具体名称，将被省略的主语"
    "补回。不要扩展、不要解释、不要加引导词。"
)


# 指代词 / 续接词 → 强信号需要改写
_FOLLOWUP_HINTS = (
    "它", "这个", "那个", "上述", "上面", "前面", "刚才",
    "继续", "再说", "再讲", "也呢", "呢", "为什么",
    "it ", "its ", "this ", "that ", "above", "previous",
    "follow up", "follow-up", "what about",
)


def _has_followup_hint(query: str) -> bool:
    s = query.strip().lower()
    if not s:
        return False
    for hint in _FOLLOWUP_HINTS:
        if hint in s:
            return True
    return False


@dataclass
class RewriteResult:
    query_used: str
    needs_rewrite: bool
    reason: str
    status: Literal["ok", "skipped", "fallback", "error"]


def _parse_response(text: str) -> dict:
    body = (text or "").strip()
    # 1) strict
    try:
        return json.loads(body)
    except Exception:
        pass
    # 2) code fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 3) regex extract
    m2 = re.search(r"\{[\s\S]*\}", body)
    if m2:
        try:
            return json.loads(m2.group(0))
        except Exception:
            pass
    return {}


async def rewrite_query_v2(
    query: str,
    history: list[dict],
    *,
    provider_id: uuid.UUID | None = None,
    model_name: str | None = None,
    registry_id: uuid.UUID | None = None,
    memory_summary: str | None = None,
) -> RewriteResult:
    """新版改写器；upstream 推荐用此入口。"""
    if not query or not query.strip():
        return RewriteResult(query_used=query, needs_rewrite=False, reason="empty",
                             status="skipped")
    if not history:
        return RewriteResult(query_used=query, needs_rewrite=False, reason="no_history",
                             status="skipped")
    has_hint = _has_followup_hint(query)
    if not has_hint and len(query.strip()) > 25:
        # 启发式：长且无指代/续接词，多半是独立问句
        return RewriteResult(query_used=query, needs_rewrite=False,
                             reason="standalone_heuristic", status="skipped")

    if not registry_id and not (provider_id and model_name):
        return RewriteResult(query_used=query, needs_rewrite=False,
                             reason="no_model_config", status="skipped")

    messages: list[dict] = [{"role": "system", "content": REWRITE_SYSTEM}]
    if memory_summary:
        messages.append({"role": "system", "content": f"长期记忆：{memory_summary[:1500]}"})
    messages.extend(history[-8:])  # 至多 8 条最近历史
    messages.append({"role": "user", "content": query})

    try:
        async with async_session() as session:
            svc = ModelService(session)
            if registry_id:
                response = await svc.chat_by_registry(registry_id, messages, max_tokens=300)
            else:
                response = await svc.chat(provider_id, model_name, messages, max_tokens=300)
    except Exception:
        logger.warning("query_rewrite_llm_failed", query=query, exc_info=True)
        return RewriteResult(query_used=query, needs_rewrite=False, reason="llm_failed",
                             status="error")

    content = ""
    try:
        content = response["choices"][0]["message"]["content"]
    except Exception:
        pass
    parsed = _parse_response(content)
    if not isinstance(parsed, dict):
        return RewriteResult(query_used=query, needs_rewrite=False, reason="parse_failed",
                             status="fallback")

    needs = bool(parsed.get("needs_rewrite", False))
    rewritten = (parsed.get("rewritten") or "").strip()
    reason = (parsed.get("reason") or "")[:80]
    if not needs or not rewritten or rewritten == query:
        return RewriteResult(query_used=query, needs_rewrite=False, reason=reason or "no_change",
                             status="skipped")
    logger.info("query_rewritten", original=query, rewritten=rewritten, reason=reason)
    return RewriteResult(query_used=rewritten, needs_rewrite=True, reason=reason, status="ok")


# ── 向后兼容 ──────────────────────────────────────────────────────

async def rewrite_query(
    query: str,
    history: list[dict],
    provider_id: uuid.UUID,
    model_name: str,
) -> str:
    """旧版接口 —— 仅返回字符串。新代码请用 rewrite_query_v2。"""
    result = await rewrite_query_v2(
        query, history, provider_id=provider_id, model_name=model_name,
    )
    return result.query_used
