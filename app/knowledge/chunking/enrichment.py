"""Chunk metadata enrichment (P24.M2).

为每个 chunk 调用系统默认 LLM 生成：
  * keywords  — 3-5 个关键词（字符串数组）
  * questions — 1-2 个用户视角问题（字符串数组）

这一步放在 chunk 处理完成后、入库前。结果写入 ``Chunk.metadata_``
(JSONB) 下的 ``keywords`` / ``questions`` 键。失败时降级：跳过该 chunk
的 enrichment，不中断整个索引流程。

设计要点：
  * 并发度默认 3，避免打挂 LLM 侧配额（可在系统层面调整）
  * 单 chunk 超时 30s；超时记录警告，保留原 metadata
  * LLM 返回解析容错：同时处理 JSON / 带代码块围栏 / 自由文本
  * 完全无 LLM 可用时（SystemSettings 未设默认模型）直接 no-op
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass

import structlog

from app.knowledge.chunking.base import ChunkResult

logger = structlog.get_logger(__name__)


CONCURRENCY = 3
PER_CHUNK_TIMEOUT = 30  # seconds


@dataclass
class EnrichmentOutput:
    keywords: list[str]
    questions: list[str]


_SYSTEM_PROMPT = """你是一名知识管理助手，帮助为文档片段生成检索辅助元数据。

仅返回严格的 JSON，不要包含任何解释或代码块围栏，格式为：
{"keywords": ["关键词1", "关键词2", ...], "questions": ["问题1?", ...]}

要求：
- keywords：3-5 个，名词短语，不含标点，长度 <= 12 字
- questions：1-2 个，用户查询视角自然表达，结尾带问号
- 全部使用原文相同语言"""


def _build_user_prompt(content: str, want_keywords: bool, want_questions: bool) -> str:
    instructions = []
    if want_keywords:
        instructions.append("抽取关键词")
    if want_questions:
        instructions.append("生成问题")
    return (
        f"请为以下文本{' 与 '.join(instructions)}：\n\n"
        f"```text\n{content.strip()[:4000]}\n```"
    )


def _parse_response(text: str, want_keywords: bool, want_questions: bool) -> EnrichmentOutput:
    """解析 LLM 回复；容错三种情况：纯 JSON、带围栏、自由文本。"""
    body = (text or "").strip()
    # 剥代码块围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if m:
        body = m.group(1)
    parsed: dict = {}
    try:
        parsed = json.loads(body)
    except Exception:
        # Best-effort 提取 {...}
        m2 = re.search(r"\{[\s\S]*\}", body)
        if m2:
            try:
                parsed = json.loads(m2.group(0))
            except Exception:
                parsed = {}
    kw = parsed.get("keywords") if isinstance(parsed, dict) else None
    qs = parsed.get("questions") if isinstance(parsed, dict) else None

    keywords = _clean_list(kw)[:5] if want_keywords else []
    questions = _clean_list(qs)[:2] if want_questions else []
    return EnrichmentOutput(keywords=keywords, questions=questions)


def _clean_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        if isinstance(item, str):
            s = item.strip().strip("。,，.")
            if s:
                out.append(s)
    return out


async def _enrich_one(
    chat_fn,
    content: str,
    want_keywords: bool,
    want_questions: bool,
) -> EnrichmentOutput:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(content, want_keywords, want_questions)},
    ]
    try:
        resp = await asyncio.wait_for(chat_fn(messages), timeout=PER_CHUNK_TIMEOUT)
    except Exception as exc:
        logger.debug("chunk_enrichment_llm_failed", error=str(exc)[:200])
        return EnrichmentOutput(keywords=[], questions=[])
    text = ""
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
    return _parse_response(text, want_keywords, want_questions)


async def enrich_chunks_async(
    chunks: list[ChunkResult],
    chat_fn,
    *,
    want_keywords: bool,
    want_questions: bool,
) -> list[EnrichmentOutput]:
    """并发丰富一批 chunks。``chat_fn`` 签名为 ``async (messages) -> dict``。

    并发度限制在 ``CONCURRENCY`` 避免冲击 provider；失败的 chunk 返回空
    EnrichmentOutput，不抛异常。
    """
    if not chunks or not (want_keywords or want_questions):
        return [EnrichmentOutput(keywords=[], questions=[]) for _ in chunks]

    sem = asyncio.Semaphore(CONCURRENCY)

    async def _task(c: ChunkResult) -> EnrichmentOutput:
        async with sem:
            return await _enrich_one(chat_fn, c.content, want_keywords, want_questions)

    return await asyncio.gather(*[_task(c) for c in chunks])


def enrich_chunks_sync(
    chunks: list[ChunkResult],
    chat_fn,
    *,
    want_keywords: bool,
    want_questions: bool,
) -> list[EnrichmentOutput]:
    """Celery task 侧同步入口 —— 内部起独立 event loop 运行并发 LLM 调用。"""
    if not chunks or not (want_keywords or want_questions):
        return [EnrichmentOutput(keywords=[], questions=[]) for _ in chunks]
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                enrich_chunks_async(
                    chunks, chat_fn,
                    want_keywords=want_keywords, want_questions=want_questions,
                )
            )
        finally:
            loop.close()
    except Exception as exc:
        logger.warning("chunk_enrichment_batch_failed", error=str(exc)[:200])
        return [EnrichmentOutput(keywords=[], questions=[]) for _ in chunks]


def build_default_chat_fn():
    """返回一个调系统默认 LLM 的 async chat 函数；未配置时返回 None。

    使用模式：
      chat_fn = build_default_chat_fn()
      if chat_fn:
          enrichments = enrich_chunks_sync(chunks, chat_fn, ...)
    """
    import asyncio as _asyncio

    async def _resolve_and_chat(messages):
        from app.core.database import async_session
        from app.model.service import ModelService
        from app.system.models import SystemSettings

        async with async_session() as db:
            row = await db.get(SystemSettings, 1)
            settings_dict = (row.settings or {}) if row else {}
            reg_id = settings_dict.get("default_llm_model_id")
            if not reg_id:
                raise RuntimeError("系统未配置默认 LLM，无法进行 chunk 元数据丰富")
            svc = ModelService(db)
            return await svc.chat_by_registry(uuid.UUID(str(reg_id)), messages)

    return _resolve_and_chat
