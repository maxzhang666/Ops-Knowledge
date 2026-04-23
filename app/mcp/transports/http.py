"""Streamable HTTP transport — MCP's production-recommended wire protocol.

Nested ``async with`` mirrors the official SDK example; AsyncExitStack lets
us expose the composite as a single context manager.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.mcp.schemas import MCPTool
from app.mcp.transports.base import MCPTransport, build_headers, tool_from_mcp


class StreamableHTTPTransport(MCPTransport):
    def __init__(self, config: dict, auth_config: dict):
        self._url = config["url"]
        self._headers = {**(config.get("headers") or {}), **build_headers(auth_config)}
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "StreamableHTTPTransport":
        self._stack = AsyncExitStack()
        read, write, _ = await self._stack.enter_async_context(
            streamablehttp_client(self._url, headers=self._headers or None)
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

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        assert self._session
        return await self._session.call_tool(name, arguments=arguments or {})
