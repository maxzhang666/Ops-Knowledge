"""Governance event write helpers (Plan 32 M1.2).

Events are always best-effort — a write failure must never fail the
retrieval or chat request that triggered it. Rebuild is driven by a
5-minute Celery batch (see ``.tasks.chunk_score_rebuild``); realtime
event writes don't touch Chunk denorm columns themselves.

All helpers accept an AsyncSession and do NOT commit — the caller's
transaction commits them together with whatever domain mutation
triggered the event.
"""
from __future__ import annotations

import uuid
from typing import Iterable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.governance.models import ChunkUsageEvent, RetrievalNoResultEvent

logger = structlog.get_logger(__name__)


async def record_hit(
    db: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    kb_id: uuid.UUID,
    message_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Called by retrieval service on every returned chunk."""
    try:
        db.add(ChunkUsageEvent(
            chunk_id=chunk_id, kb_id=kb_id,
            event_type="hit", message_id=message_id, user_id=user_id,
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("governance_hit_event_failed", chunk=str(chunk_id), error=str(e))


async def record_hits_bulk(
    db: AsyncSession,
    pairs: Iterable[tuple[uuid.UUID, uuid.UUID]],
    *,
    message_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Bulk variant — one DB round-trip for many chunks. Pairs = (chunk_id, kb_id)."""
    rows = [
        ChunkUsageEvent(
            chunk_id=c, kb_id=k, event_type="hit",
            message_id=message_id, user_id=user_id,
        )
        for c, k in pairs
    ]
    if not rows:
        return
    try:
        db.add_all(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("governance_hits_bulk_failed", count=len(rows), error=str(e))


async def record_adopted(
    db: AsyncSession,
    pairs: Iterable[tuple[uuid.UUID, uuid.UUID]],
    *,
    message_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Called by chat pipeline after extract_citations. ``pairs`` = (chunk_id, kb_id)."""
    rows = [
        ChunkUsageEvent(
            chunk_id=c, kb_id=k, event_type="adopted",
            message_id=message_id, user_id=user_id,
        )
        for c, k in pairs
    ]
    if not rows:
        return
    try:
        db.add_all(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("governance_adopted_failed", count=len(rows), error=str(e))


async def record_feedback(
    db: AsyncSession,
    pairs: Iterable[tuple[uuid.UUID, uuid.UUID]],
    *,
    sentiment: int,              # +1 positive, -1 negative, 0 reverse
    message_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Write feedback events. ``sentiment=0`` records a ``feedback_reverse``
    entry so the rebuild job can net out prior positive/negative votes
    without double counting."""
    if sentiment > 0:
        event_type = "feedback_positive"
    elif sentiment < 0:
        event_type = "feedback_negative"
    else:
        event_type = "feedback_reverse"
    rows = [
        ChunkUsageEvent(
            chunk_id=c, kb_id=k, event_type=event_type,
            message_id=message_id, user_id=user_id,
        )
        for c, k in pairs
    ]
    if not rows:
        return
    try:
        db.add_all(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("governance_feedback_failed", count=len(rows), error=str(e))


async def record_no_result(
    db: AsyncSession,
    *,
    kb_id: uuid.UUID,
    query: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Called by retrieval service when a query returns zero chunks —
    this is the primary data source for Layer 5 "knowledge gap" detection."""
    try:
        db.add(RetrievalNoResultEvent(
            kb_id=kb_id, query=query[:2000], user_id=user_id,
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("governance_no_result_failed", kb=str(kb_id), error=str(e))
