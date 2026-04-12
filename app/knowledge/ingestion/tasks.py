import structlog
from celery import shared_task
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.ingestion.parser import parse_document
from app.knowledge.models import Document, DocumentStatus, Folder, KnowledgeBase
from app.knowledge.storage.minio_service import MinIOService

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_document(self, doc_id: str) -> dict:
    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            doc = session.get(Document, doc_id)
            if doc is None:
                return {"status": "error", "message": "Document not found"}

            session.execute(
                update(Document).where(Document.id == doc_id).values(status=DocumentStatus.PROCESSING)
            )
            session.commit()

            try:
                minio = MinIOService()
                import asyncio
                file_data = asyncio.run(minio.download(doc.file_path))

                text = parse_document(file_data, doc.title)

                if len(text.strip()) < 10:
                    session.execute(
                        update(Document).where(Document.id == doc_id).values(
                            status=DocumentStatus.ERROR,
                            error_message="Document content too short (< 10 chars after parsing)",
                        )
                    )
                    session.commit()
                    return {"status": "error", "message": "Content too short"}

                from datetime import datetime, timezone
                session.execute(
                    update(Document).where(Document.id == doc_id).values(
                        status=DocumentStatus.COMPLETED,
                        processed_at=datetime.now(timezone.utc),
                    )
                )
                session.commit()

                logger.info("document_processed", doc_id=doc_id)
                return {"status": "completed", "doc_id": doc_id}

            except Exception as exc:
                session.rollback()
                session.execute(
                    update(Document).where(Document.id == doc_id).values(
                        status=DocumentStatus.ERROR,
                        error_message=str(exc)[:1000],
                    )
                )
                session.commit()
                raise self.retry(exc=exc)

    finally:
        engine.dispose()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cascade_delete_kb(self, kb_id: str) -> dict:
    engine = _get_sync_engine()
    try:
        minio = MinIOService()
        import asyncio
        deleted_files = asyncio.run(minio.delete_prefix(f"kb/{kb_id}/"))

        with Session(engine) as session:
            session.execute(delete(Document).where(Document.knowledge_base_id == kb_id))
            session.execute(delete(Folder).where(Folder.knowledge_base_id == kb_id))
            session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            session.commit()

        logger.info("kb_cascade_deleted", kb_id=kb_id, deleted_files=deleted_files)
        return {"status": "deleted", "kb_id": kb_id, "deleted_files": deleted_files}

    except Exception as exc:
        logger.error("kb_cascade_delete_failed", kb_id=kb_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        engine.dispose()
