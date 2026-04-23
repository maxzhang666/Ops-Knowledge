"""stdio transport — subprocess-based MCP servers.

**Security note**: M1 runs the subprocess directly in the API process.
M3 will route stdio through the Docker Runner (spec 04 §MCP Integration)
so untrusted server binaries execute sandboxed. Until then, admins must
only register stdio servers whose binaries they control.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.mcp.schemas import MCPTool
from app.mcp.transports.base import MCPTransport, tool_from_mcp


class StdioTransport(MCPTransport):
    def __init__(self, config: dict, auth_config: dict):
        # stdio has no wire auth — any auth_config applies via env vars
        env = dict(config.get("env") or {})
        if auth_config:
            for k, v in auth_config.items():
                if isinstance(v, str) and v:
                    env[f"MCP_AUTH_{k.upper()}"] = v
        self._params = StdioServerParameters(
            command=config["command"],
            args=list(config.get("args") or []),
            env=env or None,
        )
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "StdioTransport":
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(self._params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    async def initialize(self) -> dict:
        assert self._session
        result = await self._session.initialize()
        info = getattr(result, "serverInfo", None)
        return {
            "name": getattr(info, "name", None) if info else None,
            "version": getattr(info, "version", None) if info else None,
            "protocol_version": getattr(result, "protocolVersion", None),
        }

    async def list_tools(self) -> list[MCPTool]:
        assert self._session
        result = await self._session.list_tools()
        return [tool_from_mcp(t) for t in result.tools]

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        assert self._session
        return await self._session.call_tool(name, arguments=arguments or {})
