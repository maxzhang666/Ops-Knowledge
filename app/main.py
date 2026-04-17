from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent.router import router as agent_router
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.department.router import router as department_router
from app.knowledge.chunk_router import router as chunk_router
from app.knowledge.document_router import router as document_router
from app.knowledge.export_router import router as export_router
from app.knowledge.folder_router import router as folder_router
from app.knowledge.ingestion_router import router as ingestion_router
from app.knowledge.quality_router import router as quality_router
from app.knowledge.retrieval_router import router as retrieval_router
from app.knowledge.router import router as kb_router
from app.model.router import router as model_router
from app.system.init_router import router as init_router
from app.system.notification_router import router as notification_router
from app.system.router import router as system_router
from app.system.user_router import router as user_router

setup_logging()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


_subscriber_task = None


@app.on_event("startup")
async def _on_startup() -> None:
    global _subscriber_task
    from app.core.runtime_config import start_async_subscriber
    _subscriber_task = start_async_subscriber()
    await _recover_stuck_tasks()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    global _subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except Exception:
            pass
        _subscriber_task = None


async def _recover_stuck_tasks() -> None:
    """Re-dispatch documents whose processing was interrupted by a crash/restart."""
    from datetime import datetime, timedelta, timezone

    import structlog
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.tasks import safe_delay
    from app.knowledge.ingestion.tasks import process_document
    from app.knowledge.models import Document, DocumentStatus

    log = structlog.get_logger(__name__)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    try:
        async with async_session() as db:
            rows = (await db.execute(
                select(Document).where(
                    Document.status == DocumentStatus.PROCESSING,
                    Document.created_at < cutoff,
                )
            )).scalars().all()
            if not rows:
                return
            log.warning("startup_recover_stuck_docs", count=len(rows))
            for doc in rows:
                safe_delay(process_document, str(doc.id))
    except Exception:
        log.warning("startup_recover_failed", exc_info=True)


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(department_router, prefix=settings.API_V1_PREFIX)
app.include_router(model_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(init_router, prefix=settings.API_V1_PREFIX)
app.include_router(notification_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_router, prefix=settings.API_V1_PREFIX)
app.include_router(folder_router, prefix=settings.API_V1_PREFIX)
app.include_router(document_router, prefix=settings.API_V1_PREFIX)
app.include_router(chunk_router, prefix=settings.API_V1_PREFIX)
app.include_router(export_router, prefix=settings.API_V1_PREFIX)
app.include_router(retrieval_router, prefix=settings.API_V1_PREFIX)
app.include_router(quality_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingestion_router, prefix=settings.API_V1_PREFIX)
app.include_router(user_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)
