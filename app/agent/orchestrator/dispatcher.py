"""Dispatch a matched rule (or default) → HandlerAdapter stream.

Owns the ``on_handler_error`` policy: use_default / fallback_next /
return_error (spec 04 §on_handler_error semantics). Emits a
``handler_invoked`` event at the start so the frontend can render
'Routing to <Workflow X>' badges without waiting for first content.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.agent.orchestrator.adapters import DispatchContext, get_adapter
from app.agent.orchestrator.events import OrchestratorEvent
from app.agent.orchestrator.models import AgentRule


@dataclass
class DispatchOutcome:
    """Summary the caller (service.py) uses to write the audit row."""
    handler_latency_ms: int
    handler_status: str  # 'ok' | 'error' | 'fallback_next' | 'fallback_default'
    error: str | None = None


async def dispatch_matched(
    rule: AgentRule,
    user_message: str,
    ctx: DispatchContext,
) -> tuple[AsyncIterator[OrchestratorEvent], DispatchOutcome]:
    """Returns an async iterator plus a *pending* outcome. The caller
    must drain the iterator first; the outcome object is mutated during
    iteration (handler_status/error/latency get filled at end).
    """
    return await _dispatch(
        handler_type=rule.handler_type,
        handler_id=rule.handler_id,
        handler_config=rule.handler_config or {},
        user_message=user_message,
        ctx=ctx,
    )


async def dispatch_default(
    default: dict,
    user_message: str,
    ctx: DispatchContext,
) -> tuple[AsyncIterator[OrchestratorEvent], DispatchOutcome]:
    return await _dispatch(
        handler_type=default["handler_type"],
        handler_id=default.get("handler_id"),
        handler_config=default.get("handler_config") or {},
        user_message=user_message,
        ctx=ctx,
    )


async def _dispatch(
    *, handler_type: str, handler_id, handler_config: dict,
    user_message: str, ctx: DispatchContext,
):
    outcome = DispatchOutcome(handler_latency_ms=0, handler_status="ok")
    t0 = time.monotonic()

    adapter = get_adapter(handler_type)

    async def _stream():
        nonlocal outcome
        # Front-load the identification event so UI can render 'Routing to X'
        yield OrchestratorEvent(
            type="handler_invoked",
            data={"handler_type": handler_type, "handler_id": str(handler_id) if handler_id else None},
        )
        saw_error = False
        try:
            async for ev in adapter.dispatch(user_message, handler_id, handler_config, ctx):
                if ev.type == "error":
                    saw_error = True
                yield ev
        except Exception as e:  # noqa: BLE001
            saw_error = True
            yield OrchestratorEvent(
                type="error",
                data={"message": f"handler crashed: {str(e)[:300]}"},
            )
            outcome.error = str(e)[:500]
        finally:
            outcome.handler_latency_ms = int((time.monotonic() - t0) * 1000)
            outcome.handler_status = "error" if saw_error else "ok"

    return _stream(), outcome
