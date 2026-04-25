"""Async evaluator — Celery task that applies all judges to one message.

Spec `14-knowledge-governance.md §Layer 3/4`：在用户拿到答案后异步评估
质量，不阻塞对话路径。写 `message_evaluations` 表供 governance 聚合。

流程：
  1. 读 message + metadata_.retrieval_chunks / cited_sources
  2. 组装 judge 所需上下文 + citations
  3. 5 个 judge 并行调默认 LLM
  4. upsert 每个 metric → message_evaluations

采样：系统级 `eval_sample_rate` (SystemSettings) 控制 bulk 触发概率；
手动 API 触发永远执行。
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Iterable

import structlog
from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.knowledge.evaluation.judges import (
    JudgeResult,
    judge_answer_relevancy,
    judge_citation_accuracy,
    judge_context_precision,
    judge_faithfulness,
    judge_hallucination,
)
from app.knowledge.evaluation.models import (
    ALL_METRICS,
    METRIC_ANSWER_RELEVANCY,
    METRIC_CITATION_ACCURACY,
    METRIC_CONTEXT_PRECISION,
    METRIC_FAITHFULNESS,
    METRIC_HALLUCINATION,
    MessageEvaluation,
)

logger = structlog.get_logger(__name__)

DEFAULT_SAMPLE_RATE = 0.1


@shared_task(name="app.knowledge.evaluation.tasks.evaluate_message")
def evaluate_message(message_id: str, *, force: bool = False) -> dict:
    """异步评估一条消息。force=True 跳过采样判定（手动触发用）。"""
    return asyncio.run(_run_evaluate_message(uuid.UUID(message_id), force=force))


async def _run_evaluate_message(message_id: uuid.UUID, *, force: bool) -> dict:
    from app.chat.models import Conversation, Message
    from app.knowledge.evaluation.judges import ChatFn
    from app.system.models import SystemSettings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as db:
            # 采样判定
            if not force:
                row = await db.get(SystemSettings, 1)
                cfg = (row.settings or {}) if row else {}
                sample_rate = float(cfg.get("eval_sample_rate", DEFAULT_SAMPLE_RATE))
                if random.random() > sample_rate:
                    return {"status": "skipped_sampling", "rate": sample_rate}

            msg = await db.get(Message, message_id)
            if msg is None:
                return {"status": "error", "message": "Message not found"}
            if msg.role != "assistant":
                return {"status": "skipped_non_assistant"}
            meta = msg.metadata_ or {}
            retrieval_chunks = meta.get("retrieval_chunks") or []
            cited = meta.get("cited_sources") or []
            if not retrieval_chunks:
                return {"status": "skipped_no_retrieval"}

            # 还原 query（上一条 user 消息）
            user_msg = (await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == msg.conversation_id,
                    Message.role == "user",
                    Message.created_at < msg.created_at,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            query = user_msg.content if user_msg else ""
            answer = msg.content or ""

            # 还原 kb_id — 优先 chunk 带的 source_kb_id；否则 conversation 的 agent 绑定
            kb_ids = {c.get("source_kb_id") for c in retrieval_chunks if c.get("source_kb_id")}
            kb_id = uuid.UUID(next(iter(kb_ids))) if kb_ids else None

            chunk_texts = [
                (c.get("content_preview") or "") for c in retrieval_chunks
            ]
            # 拼成 faithfulness 用的合并 context
            context = "\n\n".join(
                f"[{i+1}] {c.get('document_title','')}\n{c.get('content_preview','')}"
                for i, c in enumerate(retrieval_chunks)
            )
            # citations 明细（Citation Accuracy）
            citations_payload = []
            for src in cited:
                idx = src.get("index")
                cid = src.get("chunk_id")
                match = next(
                    (c for c in retrieval_chunks if c.get("id") == cid),
                    None,
                )
                if match is None and idx is not None and 0 < idx <= len(retrieval_chunks):
                    match = retrieval_chunks[idx - 1]
                if match:
                    citations_payload.append({
                        "index": idx,
                        "title": src.get("title") or match.get("document_title", ""),
                        "chunk_text": match.get("content_preview") or "",
                    })

            chat_fn, judge_model = await _resolve_judge_chat_fn(db)
            if chat_fn is None:
                return {"status": "skipped_no_judge"}

        results: dict[str, JudgeResult] = await _run_all_judges(
            chat_fn, query=query, answer=answer,
            chunks=chunk_texts, context=context,
            citations=citations_payload,
        )

        async with sm() as db:
            await db.execute(
                delete(MessageEvaluation).where(MessageEvaluation.message_id == message_id)
            )
            rows = [
                MessageEvaluation(
                    message_id=message_id,
                    kb_id=kb_id,
                    metric=m,
                    score=res.score,
                    rationale=res.rationale,
                    judge_model=judge_model,
                    sample_count=res.sample_count,
                )
                for m, res in results.items()
            ]
            db.add_all(rows)
            await db.commit()

        logger.info(
            "message_evaluation_done",
            message_id=str(message_id),
            scores={m: round(r.score, 3) for m, r in results.items()},
        )
        return {
            "status": "completed",
            "message_id": str(message_id),
            "scores": {m: r.score for m, r in results.items()},
        }
    except Exception as exc:
        logger.exception("message_evaluation_failed", message_id=str(message_id), error=str(exc))
        return {"status": "error", "message": str(exc)[:300]}
    finally:
        await engine.dispose()


async def _resolve_judge_chat_fn(db: AsyncSession):
    """返回 (chat_fn, judge_model_name)。无默认 LLM 配置时返回 (None, None)。"""
    from app.model.service import ModelService
    from app.system.models import SystemSettings

    row = await db.get(SystemSettings, 1)
    cfg = (row.settings or {}) if row else {}
    reg_id = cfg.get("default_llm_model_id")
    if not reg_id:
        return None, None
    registry_id = uuid.UUID(str(reg_id))
    svc = ModelService(db)
    provider, model_id = await svc.resolve_model(registry_id)

    async def _chat(messages: list[dict]) -> dict:
        # 每次调用独立建 session — task 跨 session 复用会出问题
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sm() as inner_db:
                inner_svc = ModelService(inner_db)
                return await inner_svc.chat_by_registry(registry_id, messages)
        finally:
            await engine.dispose()

    return _chat, model_id


async def _run_all_judges(
    chat_fn, *, query: str, answer: str,
    chunks: list[str], context: str, citations: list[dict],
) -> dict[str, JudgeResult]:
    """5 个 judge 并发触发；失败的给中性 0.5 / "error"。"""
    tasks = {
        METRIC_CONTEXT_PRECISION: judge_context_precision(chat_fn, query, chunks),
        METRIC_FAITHFULNESS: judge_faithfulness(chat_fn, answer, context),
        METRIC_ANSWER_RELEVANCY: judge_answer_relevancy(chat_fn, query, answer),
        METRIC_HALLUCINATION: judge_hallucination(chat_fn, answer, context),
        METRIC_CITATION_ACCURACY: judge_citation_accuracy(chat_fn, answer, citations),
    }
    coros = list(tasks.values())
    results = await asyncio.gather(*coros, return_exceptions=True)
    out: dict[str, JudgeResult] = {}
    for metric, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            logger.debug("judge_task_exception", metric=metric, error=str(res)[:200])
            out[metric] = JudgeResult(score=0.5, rationale=f"error: {str(res)[:200]}")
        else:
            out[metric] = res
    return out


def metrics_from_results(rows: Iterable[MessageEvaluation]) -> dict[str, float]:
    """辅助：把 DB rows 压成 {metric: score}，用于汇总展示。"""
    return {r.metric: r.score for r in rows if r.metric in ALL_METRICS}
