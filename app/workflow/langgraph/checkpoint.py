"""App-wide LangGraph checkpointer singleton.

Design (Plan 29 Phase 4a):
- One ``AsyncPostgresSaver`` instance per process, initialised on FastAPI
  startup and closed on shutdown. This avoids the per-request connection
  cost of ``from_conn_string`` context-manager usage, and lets us share a
  single persistent psycopg3 connection across many executions.
- ``setup()`` is NOT called at runtime — our Alembic migration 0019 already
  created the checkpoint tables with the correct schema and populated
  ``checkpoint_migrations`` so LangGraph considers itself up-to-date.
- Connection string translated from our SQLAlchemy ``postgresql+asyncpg://``
  URL into the plain ``postgresql://`` form psycopg expects.

Returns ``None`` if import fails; callers treat ``None`` as "run without
persistent checkpointing" (in-memory only; no crash-resume or HITL).
"""
from __future__ import annotations

import logging

from app.core.config import settings

log = logging.getLogger(__name__)


_checkpointer = None  # AsyncPostgresSaver | None
_conn_ctx = None      # async context manager held open for app lifetime


def _to_psycopg_url(sqla_url: str) -> str:
    """Turn ``postgresql+asyncpg://user:pass@host/db`` into
    ``postgresql://user:pass@host/db`` (psycopg3's expected form)."""
    return sqla_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def init_checkpointer() -> None:
    """Open a long-lived ``AsyncPostgresSaver`` for this process."""
    global _checkpointer, _conn_ctx

    if _checkpointer is not None:
        return  # already initialised

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except Exception as e:  # noqa: BLE001
        log.warning(
            "checkpointer_import_failed error=%s — engine will run without "
            "persistent checkpointing (no crash-resume / HITL)",
            e,
        )
        return

    conn_string = _to_psycopg_url(settings.DATABASE_URL)
    ctx = AsyncPostgresSaver.from_conn_string(conn_string)
    # ``from_conn_string`` is an async contextmanager — hold it open for the
    # app's lifetime rather than re-entering per request.
    _conn_ctx = ctx
    _checkpointer = await ctx.__aenter__()
    log.info("checkpointer_initialised")


async def close_checkpointer() -> None:
    """Close the persistent connection on app shutdown."""
    global _checkpointer, _conn_ctx

    if _conn_ctx is None:
        return
    try:
        await _conn_ctx.__aexit__(None, None, None)
    except Exception:  # noqa: BLE001
        log.warning("checkpointer_close_failed", exc_info=True)
    _checkpointer = None
    _conn_ctx = None
    log.info("checkpointer_closed")


def get_checkpointer():
    """Return the current checkpointer (or ``None`` if not initialised /
    feature flag off / import failed). Non-raising — callers treat ``None``
    as "run without checkpointing"."""
    return _checkpointer
