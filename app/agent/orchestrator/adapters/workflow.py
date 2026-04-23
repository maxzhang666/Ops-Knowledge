"""Dispatch to a Workflow — invoke execution_service + relay events."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.agent.orchestrator.adapters.base import DispatchContext, HandlerAdapter, resolve_template
from app.agent.orchestrator.events import OrchestratorEvent


class WorkflowAdapter(HandlerAdapter):
    handler_type = "workflow"

    async def dispatch(
        self,
        user_message: str,
        handler_id: uuid.UUID | None,
        handler_config: dict,
        ctx: DispatchContext,
    ) -> AsyncIterator[OrchestratorEvent]:
        if handler_id is None:
            yield OrchestratorEvent(type="error", data={"message": "workflow handler missing handler_id"})
            return

        # input_mapping expands templates: {"query": "$message", "customer_id": "$metadata.input.customer_id"}
        mapping = handler_config.get("input_mapping") or {"query": "$message"}
        inputs = resolve_template(mapping, ctx, user_message)

        from app.workflow.execution_service import ExecutionService

        async with ctx.db_factory() as db:
            exec_svc = ExecutionService(db)
            try:
                async for event_name, data in exec_svc.run_stream(
                    workflow_id=handler_id,
                    inputs=inputs,
                    user_id=ctx.user_id,
                    trace_id=ctx.trace_id,
                ):
                    # Workflow events: node_start / node_output / content_delta /
                    # node_error / end. Forward anything content-bearing.
                    if event_name == "content_delta":
                        yield OrchestratorEvent(type="content_delta", data=_coerce(data))
                    elif event_name == "node_output":
                        # Drain the terminal Answer-node output as content
                        payload = _coerce(data)
                        if payload.get("node_type") == "answer" and payload.get("output"):
                            yield OrchestratorEvent(
                                type="content_delta",
                                data={"delta": str(payload["output"])},
                            )
                    elif event_name == "node_error":
                        yield OrchestratorEvent(type="error", data=_coerce(data))
                    # Silently drop node_start / node_end lifecycle frames —
                    # Orchestrator user stream shouldn't surface DAG internals
            except Exception as e:  # noqa: BLE001
                yield OrchestratorEvent(
                    type="error",
                    data={"message": f"workflow dispatch failed: {str(e)[:300]}"},
                )


def _coerce(data) -> dict:
    if isinstance(data, dict):
        return data
    return {"value": str(data)[:2000]}
