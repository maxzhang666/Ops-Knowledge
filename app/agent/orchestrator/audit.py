"""Write orchestrator_traces rows. Best-effort — audit failure must
never abort routing. Also updates rule hit_count / last_hit_at /
avg_latency_ms so the metrics endpoint has something to show."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import update

from app.agent.orchestrator.models import AgentRule, OrchestratorTrace

logger = structlog.get_logger(__name__)


async def record_trace(
    db_factory,
    *,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    user_message: str,
    metadata_snapshot: dict | None,
    matched_rule_id: uuid.UUID | None,
    match_type_used: str | None,
    match_latency_ms: int | None,
    classifier_output: dict | None,   # {category, confidence, cached} or None
    handler_type: str | None,
    handler_id: uuid.UUID | None,
    handler_latency_ms: int | None,
    handler_status: str | None,
    tried_rules: list[str] | None,
    error: str | None = None,
) -> None:
    try:
        async with db_factory() as db:
            row = OrchestratorTrace(
                agent_id=agent_id,
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=user_message[:5000],
                metadata_snapshot=metadata_snapshot,
                matched_rule_id=matched_rule_id,
                match_type_used=match_type_used,
                match_latency_ms=match_latency_ms,
                llm_classifier_category=(classifier_output or {}).get("category"),
                llm_classifier_confidence=(classifier_output or {}).get("confidence"),
                llm_classifier_cached=bool((classifier_output or {}).get("cached")),
                handler_type=handler_type,
                handler_id=handler_id,
                handler_latency_ms=handler_latency_ms,
                handler_status=handler_status,
                tried_rules=tried_rules,
                error=(error or "")[:2000] if error else None,
            )
            db.add(row)

            # Roll up rule hit stats in the same tx
            if matched_rule_id is not None and handler_status in ("ok", "fallback_next"):
                await _bump_rule_stats(db, matched_rule_id, handler_latency_ms or 0)

            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("orchestrator_trace_write_failed", agent=str(agent_id), error=str(e))


async def _bump_rule_stats(db, rule_id: uuid.UUID, latency_ms: int) -> None:
    """EWMA-lite: avg_latency_ms moves toward the new sample with a 1/8
    weight. Cheap and good enough for ops dashboards."""
    stmt = (
        update(AgentRule)
        .where(AgentRule.id == rule_id)
        .values(
            hit_count=AgentRule.hit_count + 1,
            last_hit_at=datetime.now(timezone.utc),
            avg_latency_ms=_ewma_expr(latency_ms),
        )
    )
    await db.execute(stmt)


def _ewma_expr(new_sample_ms: int):
    """SQL-level EWMA so we don't read-modify-write per hit.

    avg_latency_ms := coalesce(avg_latency_ms, new) * 7/8 + new * 1/8
    """
    from sqlalchemy import case, func
    from app.agent.orchestrator.models import AgentRule
    # Use a CASE so first sample (NULL) seeds directly to new value
    existing = func.coalesce(AgentRule.avg_latency_ms, new_sample_ms)
    return (existing * 7 + new_sample_ms) / 8
