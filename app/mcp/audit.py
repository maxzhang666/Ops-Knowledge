"""MCP tool-call audit log (Plan 30 M3.1).

ContextVar-based call-context propagation — the Agent runtime (or any
caller) sets ``call_context`` for the duration of an Agent turn; the
transport's ``call_tool`` wrapper reads it and records who/what/why.

Writes are best-effort: an audit failure must never abort the Agent.
The ORM row goes through its own short-lived session so we don't need
to thread a ``db`` handle down through ``MultiServerMCPClient``.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.database import async_session
from app.mcp.models import MCPToolCall

logger = structlog.get_logger(__name__)


@dataclass
class CallContext:
    """What the auditor needs to know about an MCP tool invocation.

    ``server_id`` is the canonical pointer. ``agent_id`` / ``user_id`` /
    ``conversation_id`` are soft — admin-triggered ``test_connection``
    has none of them and that's fine.
    """
    server_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    trace_id: str | None = None


call_context: ContextVar[CallContext | None] = ContextVar("mcp_call_context", default=None)


@asynccontextmanager
async def use_call_context(ctx: CallContext):
    """Scope a CallContext to an ``async with`` block — typical usage:

        async with use_call_context(CallContext(server_id=..., agent_id=...)):
            async with MultiServerMCPClient(...) as client:
                ...  # every call_tool inside records to the audit log
    """
    token = call_context.set(ctx)
    try:
        yield ctx
    finally:
        call_context.reset(token)


async def record_call(
    *,
    tool_name: str,
    args: dict | None,
    status: str,
    result: Any = None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Persist a single tool-call row. Swallows any DB failure."""
    ctx = call_context.get()
    try:
        async with async_session() as db:
            row = MCPToolCall(
                mcp_server_id=ctx.server_id if ctx else None,
                tool_name=tool_name,
                args=_safe_json(args),
                result=_safe_json(result),
                status=status,
                error=(error or "")[:2000] if error else None,
                latency_ms=latency_ms,
                agent_id=ctx.agent_id if ctx else None,
                user_id=ctx.user_id if ctx else None,
                conversation_id=ctx.conversation_id if ctx else None,
                trace_id=ctx.trace_id if ctx else None,
            )
            db.add(row)
            await db.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning("mcp_audit_write_failed", tool=tool_name, error=str(e))


def _safe_json(v: Any) -> Any:
    """Trim anything non-JSONable so the DB insert can't fail on weird payloads."""
    if v is None:
        return None
    try:
        import json
        json.dumps(v)
        return v
    except Exception:  # noqa: BLE001
        return {"repr": str(v)[:2000]}


async def measure(coro, *, tool_name: str, args: dict | None):
    """Run ``coro``, emit a ``record_call`` row, and re-raise on error.

    Used by the transport wrapper (see ``transports/base.py::_with_audit``).
    """
    start = time.monotonic()
    try:
        result = await coro
        latency = int((time.monotonic() - start) * 1000)
        await record_call(
            tool_name=tool_name, args=args, status="ok",
            result=_shape_result(result), latency_ms=latency,
        )
        return result
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        await record_call(
            tool_name=tool_name, args=args, status="error",
            result=None, error=str(exc), latency_ms=latency,
        )
        raise


def _shape_result(result: Any) -> Any:
    """MCP ``call_tool`` returns an SDK ``CallToolResult``. Flatten to a
    JSON-able shape for storage — keep the first content block's text."""
    if result is None:
        return None
    try:
        content = getattr(result, "content", None)
        if content is None:
            return {"repr": str(result)[:2000]}
        parts = []
        for p in content:
            text = getattr(p, "text", None)
            if text is not None:
                parts.append(text)
        return {"content_text": "".join(parts)[:5000]} if parts else {"repr": str(content)[:2000]}
    except Exception:  # noqa: BLE001
        return {"repr": str(result)[:2000]}
