"""Governance event-log models (Plan 32 M1).

Two separate tables — different cardinality and query patterns:

* ``ChunkUsageEvent`` — one row per hit/adopted/feedback event on a chunk.
  Queried by chunk_id + time window for per-chunk rollup, and by
  (kb_id, event_type, window) for dashboard alerts.
* ``RetrievalNoResultEvent`` — one row per zero-result retrieval. Drives
  Layer 5 "knowledge gap" clustering. No chunk FK (the whole point is
  that no matching chunk existed).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class ChunkUsageEvent(Base, UUIDMixin):
    """hit / adopted / feedback_positive / feedback_negative / feedback_reverse.

    `feedback_reverse` is emitted when a user changes or clears feedback
    — the rebuild job nets events out so a flipped vote doesn't double-count.
    """
    __tablename__ = "chunk_usage_events"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class RetrievalNoResultEvent(Base, UUIDMixin):
    __tablename__ = "retrieval_no_result_events"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
