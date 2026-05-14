"""Safe Celery task dispatch — broker 不可达时不阻塞请求，但写 task_failures 留痕。"""
import structlog

logger = structlog.get_logger(__name__)


def safe_delay(task, *args):
    """Dispatch a Celery task. Broker 不可达时记录 task_failures(state=DISPATCH_FAILED)
    以便后续 admin UI 重试 + 定期 backlog 补偿扫描兜底。

    历史：旧版本仅 logger.warning，导致 enqueue 失败完全静默——document/entry
    永远停在 pending 没人发现。#4 修复后失败入 task_failures 表，admin 能在
    "/settings/task-failures" 看到并手动重跑；同时 beat task
    vector_backlog_compensation 定期扫 chunks.vector_id IS NULL 自动补偿。
    """
    try:
        task.delay(*args)
    except Exception as exc:
        logger.warning(
            "celery_dispatch_failed",
            task=task.name, args=args, exc_info=True,
        )
        _record_dispatch_failure(task, args, exc)


def _record_dispatch_failure(task, args, exc):
    """Lazy-import TaskFailure / sync Session 避免 core ↔ system 循环依赖。"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.core.config import settings
        from app.system.celery_failures import _coerce_uuid, _extract_kb_id, _json_safe
        from app.system.models import TaskFailure

        engine = create_engine(
            settings.DATABASE_URL.replace("+asyncpg", "+psycopg"),
            pool_pre_ping=True,
        )
        try:
            with Session(engine) as session:
                tf = TaskFailure(
                    task_id=None,  # enqueue 都没成，无 celery task id
                    task_name=getattr(task, "name", "unknown") or "unknown",
                    args_json=_json_safe(list(args)) if args else None,
                    kwargs_json=None,
                    state="DISPATCH_FAILED",
                    exception=f"{type(exc).__name__}: {exc}",
                    traceback=None,
                    retries=0,
                    kb_id=_extract_kb_id(args, {}),
                )
                session.add(tf)
                session.commit()
        finally:
            engine.dispose()
        # silence unused import warning for _coerce_uuid (exported from same module)
        _ = _coerce_uuid
    except Exception:
        # 兜底失败不抛 —— 主路径已 warning 过；这里再失败也只能 log
        logger.error("dispatch_failure_record_write_failed", exc_info=True)
