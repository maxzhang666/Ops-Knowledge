"""Dispatch to another Agent by calling its chat pipeline recursively.

Cycle protection via ``DispatchContext.trace_lineage``: an agent_id
appearing twice in the lineage is an unconditional failure, short-
circuiting what would otherwise be an infinite loop.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.agent.orchestrator.adapters.base import DispatchContext, HandlerAdapter
from app.agent.orchestrator.events import OrchestratorEvent

MAX_LINEAGE_DEPTH = 5  # absolute ceiling even without a cycle


class SubAgentAdapter(HandlerAdapter):
    handler_type = "sub_agent"

    async def dispatch(
        self,
        user_message: str,
        handler_id: uuid.UUID | None,
        handler_config: dict,
        ctx: DispatchContext,
    ) -> AsyncIterator[OrchestratorEvent]:
        if handler_id is None:
            yield OrchestratorEvent(type="error", data={"message": "sub_agent handler missing handler_id"})
            return

        # Cycle / depth guard — spec §Multi-Agent Collaboration
        if handler_id in ctx.trace_lineage:
            yield OrchestratorEvent(
                type="error",
                data={"message": f"cycle detected: {handler_id} already in dispatch lineage"},
            )
            return
        if len(ctx.trace_lineage) >= MAX_LINEAGE_DEPTH:
            yield OrchestratorEvent(
                type="error",
                data={
                    "message": f"max sub-agent depth {MAX_LINEAGE_DEPTH} exceeded",
                },
            )
            return

        from app.agent.service import AgentService

        async with ctx.db_factory() as db:
            svc = AgentService(db)
            try:
                target = await svc.get_agent(handler_id)
            except Exception:
                yield OrchestratorEvent(
                    type="error",
                    data={"message": f"referenced agent {handler_id} not found"},
                )
                return

        # Dispatch into the right pipeline for this agent's type. We call
        # the pipelines directly to preserve the lineage guard rather than
        # going through the chat router (which would re-compute context).
        from app.agent.orchestrator.adapters.sse_translate import translate

        new_lineage = [*ctx.trace_lineage, handler_id]

        atype = target.agent_type or "simple"
        if atype == "simple":
            from app.chat.pipeline import run_rag_pipeline
            async for ev_name, data in run_rag_pipeline(
                agent=target, query=user_message, conversation_id=None, user_id=ctx.user_id,
            ):
                ev = translate(ev_name, data)
                if ev is not None:
                    yield ev
        elif atype == "workflow":
            from app.chat.workflow_pipeline import run_workflow_pipeline
            async for ev_name, data in run_workflow_pipeline(
                agent=target, query=user_message, conversation_id=None, user_id=ctx.user_id,
            ):
                ev = translate(ev_name, data)
                if ev is not None:
                    yield ev
        elif atype == "orchestrator":
            # Recursive orchestrator — lineage carries, re-enter route()
            from app.agent.orchestrator.service import OrchestratorService
            async with ctx.db_factory() as db:
                orch = OrchestratorService(db)
                async for ev in orch.route(
                    agent=target,
                    user_message=user_message,
                    conversation_id=None,
                    user_id=ctx.user_id,
                    metadata=ctx.metadata,
                    trace_lineage=new_lineage,
                ):
                    yield ev
        else:
            yield OrchestratorEvent(
                type="error",
                data={"message": f"unsupported sub-agent type: {atype}"},
            )
