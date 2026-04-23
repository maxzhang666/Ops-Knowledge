"""Hook the workflow EventBus → Langfuse spans.

Scheduler already publishes node_start / node_output / node_error / node_end
via plan 15's EventBus. We attach an extra subscriber that mirrors those
events to Langfuse spans — no scheduler / node code changes.

Caller usage (in workflow chat pipeline):

    trace = get_client().trace(name="workflow.execute", ...)
    instr_task = attach_bus_instrumentation(bus, trace)
    # ... run scheduler ...
    # After bus.close() fires, instr_task drains and returns.
"""
from __future__ import annotations

import asyncio
import contextvars
from typing import Any

from app.core.observability import capture_io_enabled
from app.workflow.events import EventBus

# ContextVar so node code (LLM / Classifier / Extractor) can grab the current
# trace to create Generation spans without the scheduler passing a handle through.
current_trace: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "current_trace", default=None,
)


def attach_bus_instrumentation(bus: EventBus, trace) -> asyncio.Task:
    """Spawn a consumer that maps bus events to Langfuse spans. Returns the
    task so the caller can await / cancel it."""
    q = bus.subscribe()
    open_spans: dict[str, Any] = {}

    async def _loop() -> None:
        async for ev in bus.stream(q):
            if ev.type == "node_start":
                ntype = ev.data.get("type") or "unknown"
                span = trace.span(
                    name=f"node.{ntype}",
                    metadata={"node_id": ev.node_id, "type": ntype},
                )
                open_spans[ev.node_id] = span
            elif ev.type == "node_output":
                span = open_spans.get(ev.node_id)
                if span is not None:
                    outputs = ev.data.get("outputs") or {}
                    span.update(
                        output=outputs if capture_io_enabled() else None,
                        metadata={"token_usage": ev.data.get("token_usage")},
                    )
            elif ev.type == "node_error":
                span = open_spans.get(ev.node_id)
                if span is not None:
                    span.update(level="ERROR", status_message=ev.data.get("error"))
            elif ev.type == "node_end":
                span = open_spans.pop(ev.node_id, None)
                if span is not None:
                    span.end()
            # workflow_start / workflow_end / stream_chunk: out of scope — the
            # outer trace already covers the workflow scope; streaming deltas
            # would balloon span count.

    return asyncio.create_task(_loop())
