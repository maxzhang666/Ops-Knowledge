"""Translate existing chat SSE tuples → OrchestratorEvent.

Simple Agent RAG pipeline and Workflow pipeline currently yield
``(event_name, data)`` tuples. SubAgentAdapter / SimpleAgentAdapter /
WorkflowAdapter all go through here so the mapping lives in one place.

Mapping (spec 04 §Handler Dispatcher SSE → OrchestratorEvent):
  message_start       → swallowed (Orchestrator owns lifecycle)
  thinking            → thinking (verbatim)
  retrieval_info      → retrieval_info (verbatim)
  content_delta       → content_delta (verbatim)
  message_end         → swallowed (Orchestrator emits its own at the end)
  <anything else>     → adapter_extra (debug-only; renderer suppresses in
                        non-debug mode)
"""
from __future__ import annotations

from app.agent.orchestrator.events import OrchestratorEvent

PASS_THROUGH = frozenset({"thinking", "retrieval_info", "content_delta"})
SWALLOWED = frozenset({"message_start", "message_end"})


def translate(event_name: str, data) -> OrchestratorEvent | None:
    """Return an OrchestratorEvent or None if the upstream event should
    be dropped. Callers check for None and skip yield."""
    if event_name in SWALLOWED:
        return None
    if event_name in PASS_THROUGH:
        return OrchestratorEvent(type=event_name, data=_coerce(data))
    return OrchestratorEvent(
        type="adapter_extra",
        data={"upstream_event": event_name, "payload": _coerce(data)},
    )


def _coerce(data) -> dict:
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        return {"value": data}
    return {"value": str(data)[:2000]}
