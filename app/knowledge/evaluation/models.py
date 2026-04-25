"""MessageEvaluation ORM (Plan 25 M1).

One row per (message, metric) pair. Written by ``evaluate_message``
Celery task or manual API trigger. Aggregated by governance service for
the "answer_quality" facet.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


# Supported metrics — the judge prompts / summary queries use these exact keys.
METRIC_CONTEXT_PRECISION = "context_precision"
METRIC_FAITHFULNESS = "faithfulness"
METRIC_ANSWER_RELEVANCY = "answer_relevancy"
METRIC_HALLUCINATION = "hallucination"
METRIC_CITATION_ACCURACY = "citation_accuracy"

ALL_METRICS = (
    METRIC_CONTEXT_PRECISION,
    METRIC_FAITHFULNESS,
    METRIC_ANSWER_RELEVANCY,
    METRIC_HALLUCINATION,
    METRIC_CITATION_ACCURACY,
)


class MessageEvaluation(Base, UUIDMixin):
    __tablename__ = "message_evaluations"
    __table_args__ = (
        UniqueConstraint("message_id", "metric", name="uq_message_evaluations_msg_metric"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False,
    )
    kb_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True,
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
