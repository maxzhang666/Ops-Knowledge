"""Evaluation API (Plan 25 M5).

- POST /chat/messages/{message_id}/evaluate — 手动触发（同步返回）。
- GET  /knowledge/{kb_id}/evaluation/summary — 指标聚合，供治理仪表盘。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.evaluation.models import ALL_METRICS, MessageEvaluation
from app.knowledge.evaluation.tasks import _run_evaluate_message
from app.knowledge.models import KnowledgeBase

router = APIRouter(tags=["evaluation"])


# ── Response models ───────────────────────────────────────────────

class MetricSummary(BaseModel):
    metric: str
    avg_score: float
    sample_size: int


class EvaluationSummary(BaseModel):
    kb_id: uuid.UUID
    window_days: int
    metrics: list[MetricSummary]
    overall_answer_quality: float  # 0..1，几个 answer-layer 指标的均值


class MessageEvaluationItem(BaseModel):
    metric: str
    score: float
    rationale: str | None
    sample_count: int | None
    evaluated_at: datetime


class MessageEvaluationResponse(BaseModel):
    message_id: uuid.UUID
    items: list[MessageEvaluationItem]


# ── Manual trigger ────────────────────────────────────────────────

@router.post(
    "/chat/messages/{message_id}/evaluate",
    response_model=MessageEvaluationResponse,
)
async def evaluate_message_now(
    message_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Force-run LLM-as-judge for a specific message. Blocks until judges
    finish — caller should expect ~10-30s response on a typical LLM."""
    from app.chat.models import Conversation, Message
    from app.knowledge.models import KnowledgeBase

    msg = await db.get(Message, message_id)
    if msg is None:
        raise HTTPException(404, "Message not found")
    # 权限：会话归属 → agent → kb 侧 resource check
    conv = await db.get(Conversation, msg.conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")

    result = await _run_evaluate_message(message_id, force=True)
    if result.get("status") != "completed":
        detail = result.get("message") or result.get("status")
        raise HTTPException(400, f"Evaluation failed: {detail}")

    rows = (await db.execute(
        select(MessageEvaluation).where(MessageEvaluation.message_id == message_id)
    )).scalars().all()
    return MessageEvaluationResponse(
        message_id=message_id,
        items=[
            MessageEvaluationItem(
                metric=r.metric,
                score=r.score,
                rationale=r.rationale,
                sample_count=r.sample_count,
                evaluated_at=r.evaluated_at,
            )
            for r in rows
        ],
    )


# ── Summary ───────────────────────────────────────────────────────

@router.get(
    "/knowledge/{kb_id}/evaluation/summary",
    response_model=EvaluationSummary,
)
async def evaluation_summary(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    window_days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))
    rows = (await db.execute(
        select(
            MessageEvaluation.metric,
            func.avg(MessageEvaluation.score),
            func.count(MessageEvaluation.id),
        )
        .where(
            MessageEvaluation.kb_id == kb_id,
            MessageEvaluation.evaluated_at >= cutoff,
        )
        .group_by(MessageEvaluation.metric)
    )).all()

    metrics: list[MetricSummary] = []
    for metric, avg, cnt in rows:
        if metric not in ALL_METRICS:
            continue
        metrics.append(MetricSummary(
            metric=metric,
            avg_score=round(float(avg or 0.0), 3),
            sample_size=int(cnt or 0),
        ))

    # answer_quality overall = faithfulness/relevancy/hallucination/citation 均值
    answer_metrics = {"faithfulness", "answer_relevancy", "hallucination", "citation_accuracy"}
    answer_scores = [m.avg_score for m in metrics if m.metric in answer_metrics]
    overall = round(sum(answer_scores) / len(answer_scores), 3) if answer_scores else 0.0

    return EvaluationSummary(
        kb_id=kb_id,
        window_days=window_days,
        metrics=metrics,
        overall_answer_quality=overall,
    )
