"""Retrieval ORM models (Plan 35 — auto-tuning).

Tightly scoped — only owns retrieval_logs (per-call signal store) and
retrieval_recommendations (aggregated suggestions). The chunk usage event
log lives under ``governance.models``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
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
    # Workbench fields (M1.1). NULL on legacy rows written before alembic 0044.
    params_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    # Workbench M2.1 — snapshot of the hit list at retrieval time. Lets the
    # history sidebar replay a past run without re-running the pipeline,
    # surviving even if chunks have since been reprocessed/deleted.
    results_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # M6.5 — 测试标志：True 表示来自 Workbench / Quick QA / 评估批跑等
    # 测试性场景。治理统计 / Plan 35 推荐查询应过滤 is_test=False，避免
    # 调参实验污染真实使用画像。
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Spec 25 Plan E — tag signal 观测：{tag_filter_used, routing_used,
    # routed_tags, boost_weight, boosted_count, top_canonicals}。
    # governance 聚合分析；空 dict / null 表示该次未启用任何 tag 子系统
    tag_signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
