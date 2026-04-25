"""Coverage ORMs — redundancy pairs (Plan 26 M1) + KB topics (Plan 26 T1)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class ChunkRedundancyPair(Base, UUIDMixin):
    __tablename__ = "chunk_redundancy_pairs"
    __table_args__ = (
        UniqueConstraint("chunk_a_id", "chunk_b_id", name="uq_chunk_redundancy_ordered_pair"),
        CheckConstraint("chunk_a_id < chunk_b_id", name="ck_chunk_redundancy_ordering"),
    )

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class ChunkCrossKBRedundancyPair(Base, UUIDMixin):
    """Plan 31 — cross-KB duplication 候选对。

    与 ChunkRedundancyPair 不同的是：
      - kb_a_id < kb_b_id 满足 ordering（保证一对 KB 只索引一行）
      - chunk_a_id / chunk_b_id 不强制 a<b（同 KB 内的语义保持开放，
        因为不同 KB 的 chunk_id 之间 a<b 没有业务含义）
    """
    __tablename__ = "chunk_cross_kb_redundancy_pairs"
    __table_args__ = (
        UniqueConstraint("chunk_a_id", "chunk_b_id", name="uq_cross_kb_redundancy_ordered_pair"),
        CheckConstraint("kb_a_id < kb_b_id", name="ck_cross_kb_redundancy_kb_ordering"),
    )

    kb_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    kb_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class KBTopic(Base, UUIDMixin):
    __tablename__ = "kb_topics"
    __table_args__ = (
        UniqueConstraint("kb_id", "cluster_id", name="uq_kb_topics_kb_cluster"),
    )

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    example_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
