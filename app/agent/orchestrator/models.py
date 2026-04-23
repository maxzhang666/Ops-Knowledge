import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class AgentRule(Base, UUIDMixin):
    """One row per rule — ops can query hit stats, cold rules, latency
    rankings directly in SQL. JSONB-in-Agent was rejected for exactly
    this reason (spec 04 §Data model)."""
    __tablename__ = "agent_rules"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False,
    )
    # DOUBLE PRECISION — midpoint insert on drag-reorder; N3 task rebalances
    priority: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    match_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    handler_type: Mapped[str] = mapped_column(String(20), nullable=False)
    handler_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    handler_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )
    on_handler_error: Mapped[str] = mapped_column(
        String(20), nullable=False, default="use_default", server_default="use_default",
    )
    hit_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
    )
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class OrchestratorTrace(Base, UUIDMixin):
    """Decision + dispatch audit row. ``fallback_next`` may produce two
    rows per request (the failed attempt and the eventual success),
    joined by conversation_id + user_message + created_at proximity."""
    __tablename__ = "orchestrator_traces"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    matched_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_rules.id", ondelete="SET NULL"), nullable=True,
    )
    match_type_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    match_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_classifier_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_classifier_cached: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    handler_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    handler_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    handler_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handler_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tried_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ab_group: Mapped[str | None] = mapped_column(String(4), nullable=True)  # N3
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class AgentRuleVersion(Base, UUIDMixin):
    """Rule snapshot written on each edit (Plan 31 N3.1).

    Only config-layer fields are snapshotted — not hit_count / avg_latency
    which belong to the runtime. Rollback copies a snapshot's fields
    back onto the live AgentRule row and bumps a new version.
    """
    __tablename__ = "agent_rule_versions"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_rules.id", ondelete="CASCADE"), nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    match_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    handler_type: Mapped[str] = mapped_column(String(20), nullable=False)
    handler_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    handler_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    on_handler_error: Mapped[str] = mapped_column(String(20), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
