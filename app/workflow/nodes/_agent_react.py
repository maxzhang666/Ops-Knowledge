"""Agent (ReAct) node — LLM + tools loop via LangGraph ``create_react_agent``.

Composes built-in tools (knowledge_search / code_execute / http_request)
and MCP-discovered tools from selected ``mcp_server_ids``. The node is
the single integration point the Spec 04 §Agent Runtime promises — any
Agent type (Workflow Agent today, Orchestrator Agent via Plan 31) uses
this same node.

MCP sessions are opened per-invocation via ``MultiServerMCPClient.__aenter__``
and torn down before the node returns. No persistent MCP sessions across
node executions — keeps failure modes localized and avoids long-lived
stdio subprocesses lingering after a workflow completes.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from langchain_litellm import ChatLiteLLM
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from sqlalchemy import select

from app.agent.tools import ToolContext, build_builtin_tools
from app.core.database import async_session
from app.mcp.models import MCPServer
from app.model.service import ModelService
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)

logger = structlog.get_logger(__name__)


class AgentReactNode(AbstractNode):
    manifest = NodeManifest(
        type="agent_react",
        category="agent",
        name="Agent (ReAct)",
        description="LLM + tools (built-in + MCP) in a ReAct reasoning loop.",
    )
    io = NodeIO(
        inputs={"query": {"type": "string"}},
        outputs={
            "content": {"type": "string"},
            "messages": {"type": "array"},
        },
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "model_registry_id": {"type": "string", "format": "uuid"},
                "system_prompt": {"type": "string"},
                "builtin_tools": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["knowledge_search", "code_execute", "http_request"]},
                    "default": [],
                },
                "mcp_server_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "default": [],
                },
                "kb_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "default": [],
                },
                "folder_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "default": [],
                },
                "max_iterations": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": ["model_registry_id"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not ctx.config.get("model_registry_id"):
            raise ValueError("agent_react: model_registry_id is required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        query = ctx.inputs.get("query") or ""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("agent_react: 'query' input is empty")

        registry_id = uuid.UUID(str(ctx.config["model_registry_id"]))
        system_prompt = ctx.config.get("system_prompt") or ""
        builtin_names = list(ctx.config.get("builtin_tools") or [])
        mcp_ids = list(ctx.config.get("mcp_server_ids") or [])
        kb_ids = [str(k) for k in (ctx.config.get("kb_ids") or [])]
        folder_ids = [str(f) for f in (ctx.config.get("folder_ids") or [])]

        # Resolve model via our ModelService, then wrap with litellm adapter.
        # Uses LiteLLM's provider-prefixed model string ("{type}/{id}") so any
        # provider the platform supports keeps working (openai / anthropic /
        # ollama / deepseek / …) without extra wrappers.
        async with async_session() as db:
            svc = ModelService(db)
            provider, model_id = await svc.resolve_model(registry_id)
        model_spec = f"{provider.type}/{model_id}"

        llm_kwargs: dict[str, Any] = {"model": model_spec}
        if provider.api_key:
            llm_kwargs["api_key"] = provider.api_key
        if provider.base_url:
            llm_kwargs["api_base"] = provider.base_url
        if provider.extra_config:
            llm_kwargs.update(provider.extra_config)
        llm = ChatLiteLLM(**llm_kwargs)

        tool_ctx = ToolContext(
            db_factory=async_session,
            agent_id=None,
            user_id=None,
            kb_ids=kb_ids,
            folder_ids=folder_ids,
        )
        builtin_tools = build_builtin_tools(tool_ctx, enabled=builtin_names)

        # MCP client config — empty dict disables MCP without a pointless session
        mcp_cfg = await _build_mcp_client_config(mcp_ids)
        mcp_tools: list = []
        if mcp_cfg:
            async with MultiServerMCPClient(mcp_cfg) as mc:
                mcp_tools = await mc.get_tools()
                result = await _run_agent(
                    llm, builtin_tools + mcp_tools,
                    system_prompt, query,
                    ctx.config.get("max_iterations", 8),
                )
        else:
            result = await _run_agent(
                llm, builtin_tools,
                system_prompt, query,
                ctx.config.get("max_iterations", 8),
            )

        final_msg = result["messages"][-1] if result.get("messages") else None
        content = getattr(final_msg, "content", "") if final_msg else ""
        if isinstance(content, list):
            # some models return list-of-parts; concat text parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

        return NodeResult(
            outputs={
                "content": content,
                "messages": [_serialize_message(m) for m in result.get("messages", [])],
            },
        )


async def _run_agent(llm, tools, system_prompt, query, max_iter):
    agent = create_react_agent(llm, tools)
    input_messages: list[dict] = []
    if system_prompt.strip():
        input_messages.append({"role": "system", "content": system_prompt})
    input_messages.append({"role": "user", "content": query})
    # recursion_limit caps tool-call iterations; fail fast if the loop runs away
    return await agent.ainvoke(
        {"messages": input_messages},
        config={"recursion_limit": max_iter * 2 + 5},
    )


async def _build_mcp_client_config(server_ids: list[str]) -> dict:
    """Fetch server rows and project into the ``MultiServerMCPClient`` shape.

    Empty / all-invalid input returns {} so the caller can shortcut the
    MCP session entirely.
    """
    if not server_ids:
        return {}
    ids = [uuid.UUID(str(s)) for s in server_ids]
    async with async_session() as db:
        rows = (await db.execute(
            select(MCPServer).where(MCPServer.id.in_(ids), MCPServer.is_active.is_(True))
        )).scalars().all()

    cfg: dict[str, dict] = {}
    for s in rows:
        entry = _server_to_mcp_client_entry(s)
        if entry is None:
            logger.warning("agent_react_skip_server", id=str(s.id), reason="unsupported transport")
            continue
        # Key must be a stable name; use server name but fall back to id if duplicate
        key = s.name or str(s.id)
        if key in cfg:
            key = f"{key}-{s.id}"
        cfg[key] = entry
    return cfg


def _server_to_mcp_client_entry(s: MCPServer) -> dict | None:
    """Translate our MCPServer row → langchain-mcp-adapters client dict."""
    auth_headers = _auth_headers(s.auth_config or {})
    if s.transport_type == "http":
        headers = {**(s.config.get("headers") or {}), **auth_headers}
        return {
            "transport": "streamable_http",
            "url": s.config["url"],
            **({"headers": headers} if headers else {}),
        }
    if s.transport_type == "sse":
        headers = {**(s.config.get("headers") or {}), **auth_headers}
        return {
            "transport": "sse",
            "url": s.config["url"],
            **({"headers": headers} if headers else {}),
        }
    if s.transport_type == "stdio":
        return {
            "transport": "stdio",
            "command": s.config["command"],
            "args": list(s.config.get("args") or []),
            **({"env": s.config["env"]} if s.config.get("env") else {}),
        }
    return None


def _auth_headers(auth: dict) -> dict[str, str]:
    headers: dict[str, str] = {}
    if bt := auth.get("bearer_token"):
        headers["Authorization"] = f"Bearer {bt}"
    if ak := auth.get("api_key"):
        headers[auth.get("api_key_header") or "X-API-Key"] = ak
    if extra := auth.get("extra_headers"):
        headers.update(extra)
    return headers


def _serialize_message(msg) -> dict:
    """Serialize LangChain message for DSL outputs JSON. Keep it thin —
    the canonical trace lives in Langfuse."""
    content = msg.content
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return {
        "role": getattr(msg, "type", None) or msg.__class__.__name__,
        "content": content if isinstance(content, str) else str(content),
    }
