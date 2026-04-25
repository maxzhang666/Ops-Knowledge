"""Retrieval ORM models (Plan 35 — auto-tuning).

Tightly scoped — only owns retrieval_logs (per-call signal store) and
retrieval_recommendations (aggregated suggestions). The chunk usage event
log lives under ``governance.models``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class RetrievalLog(Base, UUIDMixin):
    __tablename__ = "retrieval_logs"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class RetrievalRecommendation(Base, UUIDMixin):
    """Plan 35 M3 — 聚合输出，每 (kb_id, query_type) 一行。"""
    __tablename__ = "retrieval_recommendations"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 推荐参数 + 观测指标
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
