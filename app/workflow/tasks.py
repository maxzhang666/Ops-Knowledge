"""Celery-scheduled maintenance for the workflow domain.

Plan 20 Task 5: delete workflow_executions rows older than N days. Runs
hourly; the retention window is read from SystemSettings.workflow.retention_days
falling back to 30.

LangGraph checkpoint cleanup is NOT scheduled — conversations hard-delete
their checkpoints synchronously (see ``ConversationService.delete_conversation``),
and standalone/webhook runs' checkpoints are considered acceptable residue
at the current scale. Re-introduce a TTL task when growth warrants it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _retention_days(settings_blob: dict) -> int:
    wf = (settings_blob or {}).get("workflow") or {}
    days = wf.get("retention_days", 30)
    try:
        return max(1, int(days))
    except (TypeError, ValueError):
        return 30


@shared_task(name="app.workflow.tasks.cleanup_old_executions")
def cleanup_old_executions() -> dict:
    """Hard-delete finished workflow_executions older than the retention
    window. Relies on FK ON DELETE CASCADE on node_executions.

    Returns: {deleted_executions, retention_days, cutoff}.
    """
    # Use a sync engine / session so the Celery worker doesn't need an event
    # loop. Converts the async DATABASE_URL to the psycopg-sync driver.
    sync_url = (
        settings.DATABASE_URL
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+psycopg://", "postgresql+psycopg2://")
    )
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    from app.system.models import SystemSettings
    from app.workflow.models import WorkflowExecution

    try:
        with Session() as session:
            row = session.get(SystemSettings, 1)
            settings_blob = row.settings if row else {}
            days = _retention_days(settings_blob)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Only purge terminal rows to avoid accidentally killing a running
            # execution that's somehow been alive for > retention_days.
            result = session.execute(
                delete(WorkflowExecution).where(
                    WorkflowExecution.finished_at.is_not(None),
                    WorkflowExecution.finished_at < cutoff,
                )
            )
            session.commit()
            deleted = result.rowcount or 0

            logger.info(
                "workflow_executions_cleanup",
                deleted=deleted, retention_days=days, cutoff=cutoff.isoformat(),
            )
            return {
                "deleted_executions": deleted,
                "retention_days": days,
                "cutoff": cutoff.isoformat(),
            }
    finally:
        engine.dispose()


