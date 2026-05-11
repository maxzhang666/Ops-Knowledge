"""Golden Dataset Service + run_dataset orchestrator (Plan 38 M2).

Pure orchestration logic: 接受一个 dataset_id + agent_id，对每条问题
做 RAG（复用 retrieval_router 的 quick_qa 风格 inline pipeline 太重；
这里直接调 RetrievalService.retrieve + LLM 摘要 + Plan 25 judges）。

聚合规则：
  * run.metrics = 每个 metric 的所有问题平均
  * run.status = completed / partial（部分失败）/ error
"""
from __future__ import annotations

import asyncio
import statistics
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.evaluation.golden_models import (
    GoldenDataset, GoldenDatasetRun, GoldenQuestion, GoldenQuestionResult,
)
from app.knowledge.evaluation.judges import (
    judge_answer_relevancy, judge_citation_accuracy, judge_context_precision,
    judge_faithfulness, judge_hallucination,
)

logger = structlog.get_logger(__name__)


def aggregate_metrics(per_question_metrics: list[dict]) -> dict[str, float]:
    """对若干 per-question metric 字典做按 key 平均。空输入返回 {}。"""
    if not per_question_metrics:
        return {}
    keys: set[str] = set()
    for m in per_question_metrics:
        keys.update(m.keys())
    out: dict[str, float] = {}
    for k in keys:
        vals = [m[k] for m in per_question_metrics if k in m and m[k] is not None]
        if vals:
            out[k] = round(statistics.mean(vals), 4)
    return out


# ── DB 服务 ───────────────────────────────────────────────────────


class GoldenDatasetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # CRUD
    async def create_dataset(
        self, kb_id: uuid.UUID, *, name: str, description: str | None,
        user_id: uuid.UUID,
    ) -> GoldenDataset:
        ds = GoldenDataset(kb_id=kb_id, name=name, description=description, created_by=user_id)
        self.db.add(ds)
        await self.db.flush()
        await self.db.refresh(ds)
        return ds

    async def list_datasets(self, kb_id: uuid.UUID) -> list[GoldenDataset]:
        rows = (await self.db.execute(
            select(GoldenDataset)
            .where(GoldenDataset.kb_id == kb_id)
            .order_by(GoldenDataset.created_at.desc())
        )).scalars().all()
        return list(rows)

    async def add_question(
        self, dataset_id: uuid.UUID, *,
        question: str, expected_answer: str | None,
        expected_chunk_ids: list[str] | None,
    ) -> GoldenQuestion:
        q = GoldenQuestion(
            dataset_id=dataset_id, question=question,
            expected_answer=expected_answer,
            expected_chunk_ids=expected_chunk_ids or None,
        )
        self.db.add(q)
        await self.db.flush()
        await self.db.refresh(q)
        return q

    async def list_questions(self, dataset_id: uuid.UUID) -> list[GoldenQuestion]:
        rows = (await self.db.execute(
            select(GoldenQuestion)
            .where(GoldenQuestion.dataset_id == dataset_id)
            .order_by(GoldenQuestion.created_at.asc())
        )).scalars().all()
        return list(rows)

    async def list_runs(self, dataset_id: uuid.UUID, limit: int = 20) -> list[GoldenDatasetRun]:
        rows = (await self.db.execute(
            select(GoldenDatasetRun)
            .where(GoldenDatasetRun.dataset_id == dataset_id)
            .order_by(GoldenDatasetRun.started_at.desc())
            .limit(limit)
        )).scalars().all()
        return list(rows)


# ── Run orchestrator ─────────────────────────────────────────────


async def run_dataset(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None,
    triggered_by: uuid.UUID | None,
) -> GoldenDatasetRun:
    """同步执行：拉问题 → 跑 retrieval+LLM+judges → 聚合写库。

    保持简单：单进程串行调用，每题独立失败不影响整体。production 量大时
    应换 Celery 后台 + 进度回写，这里 v1 够用。
    """
    from app.knowledge.evaluation.tasks import _resolve_judge_chat_fn
    from app.agent.models import Agent
    from app.knowledge.retrieval.service import RetrievalService
    from app.knowledge.models import KnowledgeBase

    ds = await db.get(GoldenDataset, dataset_id)
    if ds is None:
        raise ValueError(f"GoldenDataset {dataset_id} not found")
    questions = (await db.execute(
        select(GoldenQuestion).where(GoldenQuestion.dataset_id == dataset_id)
    )).scalars().all()
    if not questions:
        raise ValueError("Dataset has no questions")

    run = GoldenDatasetRun(
        dataset_id=dataset_id, agent_id=agent_id,
        status="running", question_count=len(questions),
        triggered_by=triggered_by,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    run_id = run.id

    # 解析 LLM (judges + answer 复用同一 chat_fn）
    chat_fn, _judge_model = await _resolve_judge_chat_fn(db)
    if chat_fn is None:
        run.status = "error"
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return run

    kb = await db.get(KnowledgeBase, ds.kb_id)
    agent = await db.get(Agent, agent_id) if agent_id else None
    retrieval_svc = RetrievalService()

    failed = 0
    per_question_metrics: list[dict] = []
    for q in questions:
        try:
            metrics = await _run_single_question(
                kb=kb, agent=agent, question=q, chat_fn=chat_fn,
                retrieval_svc=retrieval_svc,
            )
        except Exception as exc:
            failed += 1
            db.add(GoldenQuestionResult(
                run_id=run_id, question_id=q.id,
                answer=None, metrics=None, error=str(exc)[:300],
            ))
            continue
        db.add(GoldenQuestionResult(
            run_id=run_id, question_id=q.id,
            answer=metrics.pop("__answer__", None),
            metrics=metrics, error=None,
        ))
        per_question_metrics.append(metrics)

    run.metrics = aggregate_metrics(per_question_metrics)
    run.status = "completed" if failed == 0 else ("partial" if failed < len(questions) else "error")
    run.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return run


async def _run_single_question(
    *, kb, agent, question: GoldenQuestion, chat_fn, retrieval_svc,
) -> dict:
    """对一题执行：retrieve → LLM 答 → 5 judges。失败抛异常。"""
    from app.chat.prompt import format_context_chunks

    # 1. retrieve
    retrieval_kwargs: dict = {
        "query": question.question,
        "kb_ids": [str(kb.id)],
        "top_k": 5,
        # 黄金集评估批跑不是真实用户使用，跳过治理事件 + 标记 is_test
        "is_test": True,
    }
    if kb.embedding_model_id:
        retrieval_kwargs["embedding_model_registry_id"] = kb.embedding_model_id
    elif kb.embedding_provider_id and kb.embedding_model_name:
        retrieval_kwargs["embedding_provider_id"] = kb.embedding_provider_id
        retrieval_kwargs["embedding_model_name"] = kb.embedding_model_name
    else:
        raise RuntimeError("KB embedding not configured")
    result = await retrieval_svc.retrieve(**retrieval_kwargs)

    chunks = [
        {"content": r.content, "title": r.title, "chunk_id": r.chunk_id, "score": r.score}
        for r in result.results
    ]
    context = format_context_chunks(
        [{"content": c["content"], "title": c["title"]} for c in chunks],
        max_tokens=4000,
    )

    # 2. LLM 答
    sys_prompt = (
        "You are a knowledge assistant. Answer using ONLY the reference context. "
        "Cite [N] for each claim.\n\nReference:\n" + context
    )
    answer_resp = await chat_fn([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": question.question},
    ])
    answer = ""
    try:
        answer = (answer_resp.get("choices") or [])[0].get("message", {}).get("content", "")
    except Exception:
        pass
    if not answer:
        raise RuntimeError("LLM returned empty answer")

    # 3. 5 judges 并发
    citations = [
        {"index": i + 1, "title": c["title"], "chunk_text": c["content"][:600]}
        for i, c in enumerate(chunks)
    ]
    cp, faith, rel, halluc, cite = await asyncio.gather(
        judge_context_precision(chat_fn, question.question, [c["content"] for c in chunks]),
        judge_faithfulness(chat_fn, answer, context),
        judge_answer_relevancy(chat_fn, question.question, answer),
        judge_hallucination(chat_fn, answer, context),
        judge_citation_accuracy(chat_fn, answer, citations),
        return_exceptions=False,
    )
    metrics = {
        "context_precision": cp.score,
        "faithfulness": faith.score,
        "answer_relevancy": rel.score,
        "hallucination": halluc.score,
        "citation_accuracy": cite.score,
        "__answer__": answer,
    }
    return metrics
