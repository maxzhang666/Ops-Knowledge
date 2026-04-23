"""SSE transport — deprecated by MCP spec in favor of Streamable HTTP.

Kept strictly for talking to legacy servers that haven't migrated yet.
New integrations should use ``transport_type='http'``.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from app.mcp.schemas import MCPTool
from app.mcp.transports.base import MCPTransport, build_headers, tool_from_mcp


class SSETransport(MCPTransport):
    def __init__(self, config: dict, auth_config: dict):
        self._url = config["url"]
        self._headers = {**(config.get("headers") or {}), **build_headers(auth_config)}
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "SSETransport":
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(
            sse_client(self._url, headers=self._headers or None)
        )
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

    async def _do_call_tool(self, name: str, arguments: dict | None) -> Any:
        assert self._session
        return await self._session.call_tool(name, arguments=arguments or {})
