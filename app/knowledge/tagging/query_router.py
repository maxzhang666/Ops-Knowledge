"""Spec 25 §5.4 — L5 LLM Query Routing。

检索前调小模型从 query 中抽出"语义上相关的字典 canonical 列表"，作为
tag_filter.any_of 自动注入。用户在前端可看到推断结果并 toggle 禁用本次路由。

设计原则：
- 失败完全静默退化（返 []），retrieval 路径不被路由子系统阻塞
- LLM 调用复用 kb_tag_settings.auto_tag_llm_model_id（与 auto_tag 共用模型）
- 用户已显式传 tag_filter.any_of 时不路由（用户意图优先）
- prompt 注入 KB 字典 active canonicals 引导命名一致性（同 LLM extractor 思路）
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import structlog

from app.knowledge.tagging.models import KBTagSettings, TagDictionary
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


_PROMPT_TEMPLATE = """你是一个查询路由助手。给定用户的检索 query 和当前知识库的标签字典，请输出 query 在语义上"应该被限定到"的标签列表（最多 {max_n} 个）。

要求：
1. 仅输出 JSON 数组，格式：["标签1", "标签2"]
2. 必须从给定的字典列表中选择标签；不要创造新词
3. 如果 query 与任何字典标签都无明显语义相关，输出空数组 []
4. 偏严格：宁可少选不要错选，避免把无关 tag 加进过滤反而导致 0 召回

字典列表（{dict_count} 个 active canonical）：
{canonicals}

用户 query: {query}

仅输出 JSON 数组，不要任何额外文本：
"""

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _extract_json_array(text: str) -> list:
    if not text:
        return []
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


async def route_query_to_tags(
    db: AsyncSession,
    kb_id: uuid.UUID,
    query: str,
    model_svc: Any,
    *,
    max_n: int = 5,
) -> list[str]:
    """对 query 路由到 KB 字典 canonical 子集；失败 / 未启用 / 字典空都返 []。

    返回的 tag 列表已通过字典 lookup 校验（仅 active canonical），调用方可直接
    塞进 tag_filter.any_of。
    """
    # 1. 读 KB tag_settings
    settings_row = await db.get(KBTagSettings, kb_id)
    if settings_row is None or not settings_row.tag_routing_enabled:
        return []
    if settings_row.auto_tag_llm_model_id is None:
        # routing 启用但没配 LLM 模型 → 跳过
        logger.info(
            "query_route_skipped",
            kb_id=str(kb_id), reason="no_llm_model",
        )
        return []

    # 2. 拉 KB 字典 active canonicals
    rows = (await db.execute(
        select(TagDictionary.canonical, TagDictionary.usage_count)
        .where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(False),
        )
        .order_by(TagDictionary.usage_count.desc())
    )).all()
    if not rows:
        return []
    canonicals = [r[0] for r in rows]
    canon_set = {c for c in canonicals}
    # prompt 中 canonical 列表只取前 200，避免 prompt 过大
    sample = canonicals[:200]
    canonicals_str = " / ".join(sample)
    if len(canonicals) > 200:
        canonicals_str += f"（…共 {len(canonicals)} 个，仅展示 200）"

    # 3. 调 LLM
    prompt = _PROMPT_TEMPLATE.format(
        max_n=max_n,
        dict_count=len(canonicals),
        canonicals=canonicals_str,
        query=(query or "").strip()[:500],
    )
    try:
        response = await model_svc.chat_by_registry(
            settings_row.auto_tag_llm_model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # 路由要稳定可复现
            max_tokens=200,
        )
    except Exception:
        logger.warning(
            "query_route_llm_failed",
            kb_id=str(kb_id), exc_info=True,
        )
        return []

    # 4. 解析输出
    raw_text = ""
    try:
        choices = response.get("choices") or []
        if choices:
            raw_text = (choices[0].get("message") or {}).get("content") or ""
    except (AttributeError, IndexError):
        return []

    parsed = _extract_json_array(raw_text)
    if not isinstance(parsed, list):
        return []

    # 5. 过滤：只保留字典中实际存在的 canonical（防 LLM 幻觉）
    out: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item or item in seen:
            continue
        if item not in canon_set:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= max_n:
            break
    logger.info(
        "query_routed",
        kb_id=str(kb_id), query_len=len(query or ""),
        routed_count=len(out), routed=out[:5],
    )
    return out
