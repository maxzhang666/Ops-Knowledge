"""HandlerAdapter protocol + dispatch context.

All handler_types implement the same ``dispatch`` signature so audit,
token accounting, tracing, and error recovery are written once in
``dispatcher.py`` instead of copy-pasted across paths.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.orchestrator.events import OrchestratorEvent


@dataclass
class DispatchContext:
    agent_id: uuid.UUID
    conversation_id: uuid.UUID | None
    user_id: uuid.UUID | None
    trace_id: str
    # Chain of agent_ids already dispatched in this route — SubAgent cycle guard.
    trace_lineage: list[uuid.UUID] = field(default_factory=list)
    db_factory: Callable = None  # async session factory
    metadata: dict = field(default_factory=dict)  # {trusted, input}


class HandlerAdapter(ABC):
    handler_type: str  # class attr on concrete subclasses

    @abstractmethod
    async def dispatch(
        self,
        user_message: str,
        handler_id: uuid.UUID | None,
        handler_config: dict,
        ctx: DispatchContext,
    ) -> AsyncIterator[OrchestratorEvent]:
        """Yield OrchestratorEvent until the handler is done.

        Must NOT emit ``message_end`` — the Orchestrator pipeline owns
        the final message lifecycle event.
        """
        raise NotImplementedError
        if False:  # pragma: no cover - make this a generator by type
            yield


def get_adapter(handler_type: str) -> HandlerAdapter:
    """Plain-function dispatch matches the spec's handler_type enum."""
    # Lazy imports to keep this module dependency-free at top level
    if handler_type == "simple_agent":
        from app.agent.orchestrator.adapters.simple_agent import SimpleAgentAdapter
        return SimpleAgentAdapter()
    if handler_type == "workflow":
        from app.agent.orchestrator.adapters.workflow import WorkflowAdapter
        return WorkflowAdapter()
    if handler_type == "mcp_tool":
        from app.agent.orchestrator.adapters.mcp_tool import MCPToolAdapter
        return MCPToolAdapter()
    if handler_type == "sub_agent":
        from app.agent.orchestrator.adapters.sub_agent import SubAgentAdapter
        return SubAgentAdapter()
    raise ValueError(f"Unsupported handler_type: {handler_type}")


def resolve_template(template: Any, ctx: DispatchContext, user_message: str) -> Any:
    """Expand ``$message`` / ``$metadata.foo`` / ``$user.id`` in string
    templates. Non-string values pass through.

    Used by WorkflowAdapter ``input_mapping`` and MCPToolAdapter
    ``arg_template``.
    """
    if isinstance(template, dict):
        return {k: resolve_template(v, ctx, user_message) for k, v in template.items()}
    if isinstance(template, list):
        return [resolve_template(v, ctx, user_message) for v in template]
    if not isinstance(template, str):
        return template
    if not template.startswith("$"):
        return template
    if template == "$message":
        return user_message
    if template.startswith("$metadata."):
        path = template[len("$metadata."):]
        cur: Any = ctx.metadata
        for seg in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(seg)
            if cur is None:
                return None
        return cur
    if template.startswith("$user."):
        seg = template[len("$user."):]
        trusted = (ctx.metadata or {}).get("trusted", {}).get("user", {})
        return trusted.get(seg)
    return template
