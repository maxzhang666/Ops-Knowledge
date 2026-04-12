from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update

from app.core.celery import celery_app
from app.core.config import settings
from app.knowledge.models import Document, DocumentStatus, KBStatus, KnowledgeBase

logger = structlog.get_logger(__name__)

STALE_THRESHOLD_MINUTES = 60


@celery_app.task(name="app.system.tasks.consistency_scan")
def consistency_scan():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    try:
        with Session(engine) as session:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)

            # Find stale processing documents (stuck > 1hr)
            stale_docs = session.execute(
                select(Document.id).where(
                    Document.status == DocumentStatus.PROCESSING,
                    Document.updated_at < cutoff,
                )
            ).scalars().all()

            if stale_docs:
                session.execute(
                    update(Document)
                    .where(Document.id.in_(stale_docs))
                    .values(status=DocumentStatus.ERROR, error_message="Processing timed out (stuck > 1hr)")
                )
                logger.warning("consistency_scan_stale_docs", count=len(stale_docs))

            # Find stale deleting KBs (stuck > 1hr)
            stale_kbs = session.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.status == KBStatus.DELETING,
                    KnowledgeBase.updated_at < cutoff,
                )
            ).scalars().all()

            if stale_kbs:
                from app.knowledge.ingestion.tasks import cleanup_kb
                for kb_id in stale_kbs:
                    cleanup_kb.delay(str(kb_id))
                logger.warning("consistency_scan_stale_kbs", count=len(stale_kbs))

            session.commit()
            logger.info(
                "consistency_scan_complete",
                stale_docs=len(stale_docs),
                stale_kbs=len(stale_kbs),
            )
    finally:
        engine.dispose()
