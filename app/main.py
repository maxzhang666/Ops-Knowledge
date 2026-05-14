from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Eager-instantiate the Celery app so its broker (REDIS_URL) becomes the
# "current app" used by ``@shared_task`` dispatches from API handlers.
# Without this, ``task.delay()`` from a request thread falls back to
# Celery's global default broker (``pyamqp://guest@localhost:5672//``),
# silently fails to publish, and the document stays stuck in "pending"
# forever because the worker never sees the message.
import app.core.celery  # noqa: F401

from app.agent.orchestrator.router import router as orchestrator_router
from app.agent.router import router as agent_router
from app.auth.router import router as auth_router
from app.auth.sso_router import router as auth_sso_router
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
from app.knowledge.coverage.router import router as kb_coverage_router
from app.knowledge.evaluation.router import router as evaluation_router
from app.knowledge.review.router import router as kb_review_router
from app.knowledge.unit_router import router as kb_unit_router
from app.knowledge.entry_router import router as kb_entry_router
from app.knowledge.sources_router import router as kb_sources_router
# Plan 40 M1 — 触发 IngestionPlugin 注册（FileSourcePlugin 等）。
# 必须在 router 导入之后、app.include_router 调用之前完成。
import app.knowledge.sources  # noqa: F401
from app.knowledge.governance.router import router as kb_governance_router
from app.knowledge.ingestion_router import router as ingestion_router
from app.knowledge.retrieval_router import router as retrieval_router
from app.knowledge.router import router as kb_router
from app.mcp.router import router as mcp_router
from app.model.router import router as model_router
from app.system.init_router import router as init_router
from app.knowledge.tagging.router import router as tag_dictionary_router
from app.knowledge.tagging.kb_settings import router as kb_tag_settings_router
from app.system.milvus_router import router as system_milvus_router
from app.system.notification_router import router as notification_router
from app.system.router import router as system_router
from app.system.task_failures_router import router as task_failures_router
from app.system.user_router import router as user_router
from app.workflow.node_router import router as workflow_node_router
from app.workflow.router import router as workflow_router
from app.workflow.webhook_router import router as workflow_webhook_router
from app.workflow.ws_router import router as workflow_ws_router

setup_logging()


_subscriber_task = None
_event_bus_task = None
_cancel_bus_task = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """App startup + shutdown in one context manager (FastAPI-recommended
    replacement for the deprecated ``@app.on_event`` pair).

    Startup:
      - Runtime-config pub/sub subscriber
      - Auto-load built-in workflow nodes
      - Cross-domain event bus subscriber (Plan 21/23)
      - Workflow cancel fan-out subscriber (Plan 20 Task 4)
      - LangGraph checkpointer (Plan 29 Phase 4a)
      - Recover documents stuck in PROCESSING after a crash

    Shutdown: cancel each task we own + close checkpointer + final Langfuse flush.
    """
    global _subscriber_task, _event_bus_task, _cancel_bus_task

    from app.core.runtime_config import start_async_subscriber
    from app.workflow.nodes.registry import load_builtin_nodes

    _subscriber_task = start_async_subscriber()
    load_builtin_nodes()

    # Side-effect import registers @on handlers BEFORE the subscriber starts,
    # so no events race past an empty handler registry.
    import app.observability.bus_relay  # noqa: F401
    # Plan 27 M2：governance alert → workflow trigger 需要在 subscriber 启动前注册
    import app.workflow.governance_trigger  # noqa: F401
    from app.integration.event_bus import start_subscriber as start_event_bus
    _event_bus_task = await start_event_bus()

    from app.workflow.cancel_bus import start_cancel_subscriber
    from app.workflow.router import _live_tasks
    _cancel_bus_task = await start_cancel_subscriber(_live_tasks)

    from app.workflow.langgraph.checkpoint import init_checkpointer
    await init_checkpointer()

    # Plan 27 M3 — seed governance workflow templates (idempotent)
    try:
        from app.core.database import async_session as async_session_factory
        from app.workflow.governance_templates import seed_governance_templates
        async with async_session_factory() as seed_db:
            await seed_governance_templates(seed_db)
    except Exception:  # noqa: BLE001
        pass

    await _recover_stuck_tasks()

    try:
        yield
    finally:
        for task in (_subscriber_task, _event_bus_task, _cancel_bus_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except Exception:  # noqa: BLE001
                    pass
        _subscriber_task = _event_bus_task = _cancel_bus_task = None

        try:
            from app.workflow.langgraph.checkpoint import close_checkpointer
            await close_checkpointer()
        except Exception:  # noqa: BLE001
            pass

        # Plan 23 Task 6: final Langfuse flush so in-memory spans from long
        # SSE runs don't vanish at shutdown.
        try:
            from app.core.observability import flush as _langfuse_flush
            _langfuse_flush()
        except Exception:  # noqa: BLE001
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)
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


@app.middleware("http")
async def _flush_langfuse_after_response(request, call_next):
    """Kick off a background Langfuse flush after each HTTP response.
    Catches traces from short-lived requests; long SSE streams are covered
    by the shutdown hook."""
    response = await call_next(request)
    try:
        import asyncio as _asyncio
        from app.core.observability import flush as _langfuse_flush
        _asyncio.create_task(_asyncio.to_thread(_langfuse_flush))
    except Exception:
        pass
    return response


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
app.include_router(auth_sso_router, prefix=settings.API_V1_PREFIX)
app.include_router(department_router, prefix=settings.API_V1_PREFIX)
app.include_router(model_router, prefix=settings.API_V1_PREFIX)
app.include_router(mcp_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_milvus_router, prefix=settings.API_V1_PREFIX)
app.include_router(task_failures_router, prefix=settings.API_V1_PREFIX)
app.include_router(init_router, prefix=settings.API_V1_PREFIX)
app.include_router(notification_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_router, prefix=settings.API_V1_PREFIX)
app.include_router(folder_router, prefix=settings.API_V1_PREFIX)
app.include_router(document_router, prefix=settings.API_V1_PREFIX)
app.include_router(chunk_router, prefix=settings.API_V1_PREFIX)
app.include_router(export_router, prefix=settings.API_V1_PREFIX)
app.include_router(retrieval_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_governance_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_coverage_router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluation_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_review_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_unit_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_entry_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_sources_router, prefix=settings.API_V1_PREFIX)
app.include_router(tag_dictionary_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_tag_settings_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingestion_router, prefix=settings.API_V1_PREFIX)
app.include_router(user_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_router, prefix=settings.API_V1_PREFIX)
app.include_router(orchestrator_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_node_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_ws_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_webhook_router, prefix=settings.API_V1_PREFIX)
