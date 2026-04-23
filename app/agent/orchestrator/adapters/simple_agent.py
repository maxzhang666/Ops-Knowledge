"""Dispatch to a Simple Agent — wrap its RAG pipeline stream.

Uses the existing ``run_rag_pipeline`` (spec 16) so we don't duplicate
retrieval / prompt / streaming logic. The sub-agent's conversation_id
is distinct from the Orchestrator's — Simple Agent pipeline creates its
own conversation row; the Orchestrator keeps *its* own conversation for
the outer user view.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.agent.orchestrator.adapters.base import DispatchContext, HandlerAdapter
from app.agent.orchestrator.adapters.sse_translate import translate
from app.agent.orchestrator.events import OrchestratorEvent


class SimpleAgentAdapter(HandlerAdapter):
    handler_type = "simple_agent"

    async def dispatch(
        self,
        user_message: str,
        handler_id: uuid.UUID | None,
        handler_config: dict,
        ctx: DispatchContext,
    ) -> AsyncIterator[OrchestratorEvent]:
        if handler_id is None:
            yield OrchestratorEvent(
                type="error",
                data={"message": "simple_agent handler missing handler_id"},
            )
            return

        # Lazy imports — keep base adapter module cheap at startup
        from app.agent.service import AgentService
        from app.chat.pipeline import run_rag_pipeline

        async with ctx.db_factory() as db:
            agent_svc = AgentService(db)
            try:
                target_agent = await agent_svc.get_agent(handler_id)
            except Exception:
                yield OrchestratorEvent(
                    type="error",
                    data={"message": f"referenced simple_agent {handler_id} not found"},
                )
                return

        # run_rag_pipeline manages its own session internally. We pass the
        # outer user_id so audit / cost tracking attributes correctly.
        async for event_name, data in run_rag_pipeline(
            agent=target_agent,
            query=user_message,
            conversation_id=None,   # sub-conversation, throwaway
            user_id=ctx.user_id,
        ):
            ev = translate(event_name, data)
            if ev is not None:
                yield ev
