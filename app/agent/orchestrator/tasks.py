"""Celery beat tasks for Orchestrator governance (Plan 31 N3.5).

- ``trace_retention``: 清 > N 天（默认 30）的 orchestrator_traces 行；
  运营指标依赖最近窗口而非全量历史，老数据膨胀 DB 得不偿失。
- ``priority_rebalance``: 长期拖拽重排可能让 DOUBLE PRECISION priority
  精度逼近相邻（1e-15 级），定期把每个 Agent 的规则按当前顺序重新
  写成 10 / 20 / 30 … 整数 spacing。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = structlog.get_logger(__name__)

DEFAULT_RETENTION_DAYS = 30
REBALANCE_STEP = 10.0


@shared_task(name="app.agent.orchestrator.tasks.trace_retention")
def trace_retention() -> dict:
    """Celery entry — delegates to async impl in a fresh loop."""
    return asyncio.run(_run_trace_retention())


async def _run_trace_retention(retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    from app.agent.orchestrator.models import OrchestratorTrace
    from app.system.models import SystemSettings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sessionmaker() as db:
            # Allow admin override via SystemSettings
            try:
                row = await db.get(SystemSettings, 1)
                if row and row.settings:
                    retention_days = int(
                        row.settings.get("orchestrator_trace_retention_days", retention_days)
                    )
            except Exception:  # noqa: BLE001
                pass

            cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
            result = await db.execute(
                delete(OrchestratorTrace).where(OrchestratorTrace.created_at < cutoff)
            )
            deleted = result.rowcount or 0
            await db.commit()
            logger.info(
                "orch_trace_retention_done",
                deleted=deleted, retention_days=retention_days,
            )
            return {"deleted": deleted, "retention_days": retention_days}
    finally:
        await engine.dispose()


@shared_task(name="app.agent.orchestrator.tasks.priority_rebalance")
def priority_rebalance() -> dict:
    return asyncio.run(_run_priority_rebalance())


async def _run_priority_rebalance() -> dict:
    """Re-space priorities to 10, 20, 30 … per Agent when any two are
    closer than the threshold. Preserves the current sort order."""
    from app.agent.models import Agent
    from app.agent.orchestrator.cache import invalidate
    from app.agent.orchestrator.models import AgentRule

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    rebalanced_agents = 0
    rebalanced_rules = 0
    try:
        async with sessionmaker() as db:
            # Only look at orchestrator agents that actually have rules
            agent_ids = (await db.execute(
                select(Agent.id).where(Agent.agent_type == "orchestrator")
            )).scalars().all()

            for agent_id in agent_ids:
                rules = list((await db.execute(
                    select(AgentRule)
                    .where(AgentRule.agent_id == agent_id)
                    .order_by(AgentRule.priority.asc())
                )).scalars().all())
                if len(rules) < 2:
                    continue
                # Check precision collision: any gap smaller than 1e-6 = rewrite
                gaps = [rules[i + 1].priority - rules[i].priority for i in range(len(rules) - 1)]
                if min(gaps) > 1e-6:
                    continue
                for i, r in enumerate(rules):
                    r.priority = (i + 1) * REBALANCE_STEP
                rebalanced_agents += 1
                rebalanced_rules += len(rules)
                invalidate(agent_id)
            await db.commit()
        logger.info(
            "orch_priority_rebalance_done",
            agents=rebalanced_agents, rules=rebalanced_rules,
        )
        return {"agents": rebalanced_agents, "rules": rebalanced_rules}
    finally:
        await engine.dispose()
