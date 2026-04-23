"""Dispatch to a single MCP tool call.

Stateless: open transient MCP session, call tool, stringify result,
close. No ReAct loop — this is a direct tool invocation selected by
the rule engine. For reasoning-over-tools use Workflow + agent_react.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.agent.orchestrator.adapters.base import DispatchContext, HandlerAdapter, resolve_template
from app.agent.orchestrator.events import OrchestratorEvent


class MCPToolAdapter(HandlerAdapter):
    handler_type = "mcp_tool"

    async def dispatch(
        self,
        user_message: str,
        handler_id: uuid.UUID | None,  # mcp_server_id
        handler_config: dict,
        ctx: DispatchContext,
    ) -> AsyncIterator[OrchestratorEvent]:
        tool_name = handler_config.get("tool_name")
        if handler_id is None or not tool_name:
            yield OrchestratorEvent(
                type="error",
                data={"message": "mcp_tool handler requires handler_id (server) + tool_name"},
            )
            return

        arg_template = handler_config.get("arg_template") or {"input": "$message"}
        args = resolve_template(arg_template, ctx, user_message)

        from app.mcp.audit import CallContext, use_call_context
        from app.mcp.service import MCPServerService
        from app.mcp.transports import get_transport

        try:
            async with ctx.db_factory() as db:
                mcp_svc = MCPServerService(db)
                server = await mcp_svc.get_server(handler_id)
        except Exception:
            yield OrchestratorEvent(
                type="error",
                data={"message": f"mcp server {handler_id} not found"},
            )
            return

        audit_ctx = CallContext(
            server_id=server.id,
            agent_id=ctx.agent_id,
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            trace_id=ctx.trace_id,
        )

        yield OrchestratorEvent(
            type="handler_invoked",
            data={"handler_type": "mcp_tool", "tool_name": tool_name},
        )

        async with use_call_context(audit_ctx):
            try:
                async with get_transport(server) as t:
                    await t.initialize()
                    result = await t.call_tool(tool_name, arguments=args)
            except Exception as e:  # noqa: BLE001
                yield OrchestratorEvent(
                    type="error",
                    data={"message": f"tool call failed: {str(e)[:300]}"},
                )
                return

        yield OrchestratorEvent(
            type="content_delta",
            data={"delta": _stringify_result(result)},
        )


def _stringify_result(result) -> str:
    # MCP CallToolResult has ``content`` list of TextContent / ImageContent etc.
    content = getattr(result, "content", None)
    if content is None:
        return str(result)[:5000]
    out: list[str] = []
    for p in content:
        text = getattr(p, "text", None)
        if text is not None:
            out.append(text)
    return ("\n".join(out) if out else str(content)[:5000])[:5000]
