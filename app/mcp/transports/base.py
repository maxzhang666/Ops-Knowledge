"""Transport abstraction shared by HTTP / SSE / stdio.

``MCPTransport`` is a short-lived async context manager:

    async with get_transport(server) as t:
        await t.initialize()
        tools = await t.list_tools()

The context manager owns the underlying ``mcp.ClientSession`` — exit
closes the wire. Don't hold a transport across requests; open one per
operation. This keeps failure modes localized (stale session, broken
pipe) and matches how the official SDK's context managers are designed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.mcp.schemas import MCPTool


class MCPTransport(ABC):
    """Async context manager wrapping an ``mcp.ClientSession``."""

    @abstractmethod
    async def __aenter__(self) -> "MCPTransport": ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    @abstractmethod
    async def initialize(self) -> dict: ...

    @abstractmethod
    async def list_tools(self) -> list[MCPTool]: ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict | None = None) -> Any: ...


def get_transport(server) -> MCPTransport:
    """Dispatch to the concrete transport implementation.

    Kept as a plain function (not a registry) — three hard-coded
    branches match the protocol; new transports are rare and should
    land in the spec first.
    """
    # Local imports avoid circular import + keep optional deps lazy
    from app.mcp.transports.http import StreamableHTTPTransport
    from app.mcp.transports.sse import SSETransport
    from app.mcp.transports.stdio import StdioTransport

    t = server.transport_type
    if t == "http":
        return StreamableHTTPTransport(server.config, server.auth_config or {})
    if t == "sse":
        return SSETransport(server.config, server.auth_config or {})
    if t == "stdio":
        return StdioTransport(server.config, server.auth_config or {})
    raise ValueError(f"Unsupported transport_type: {t}")


def build_headers(auth_config: dict | None) -> dict[str, str]:
    """Translate our AuthConfig shape → HTTP headers the MCP SDK passes through."""
    if not auth_config:
        return {}
    headers: dict[str, str] = {}
    if bt := auth_config.get("bearer_token"):
        headers["Authorization"] = f"Bearer {bt}"
    if ak := auth_config.get("api_key"):
        headers[auth_config.get("api_key_header") or "X-API-Key"] = ak
    if extra := auth_config.get("extra_headers"):
        headers.update(extra)
    return headers


def tool_from_mcp(t) -> MCPTool:
    """Normalize the SDK ``Tool`` object into our ``MCPTool`` shape."""
    return MCPTool(
        name=t.name,
        description=getattr(t, "description", None),
        input_schema=getattr(t, "inputSchema", None) or getattr(t, "input_schema", None),
    )
