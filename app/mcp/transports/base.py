"""Transport abstraction shared by HTTP / SSE / stdio.

``MCPTransport`` is a short-lived async context manager:

    async with get_transport(server) as t:
        await t.initialize()
        tools = await t.list_tools()

The context manager owns the underlying ``mcp.ClientSession`` — exit
closes the wire. Don't hold a transport across requests; open one per
operation. This keeps failure modes localized (stale session, broken
pipe) and matches how the official SDK's context managers are designed.

``call_tool`` is audited via ``app.mcp.audit`` and retries once on
transient errors (timeout / connection reset) — both concerns live here
so all 3 transports share the code.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import structlog

from app.mcp.audit import measure
from app.mcp.schemas import MCPTool

logger = structlog.get_logger(__name__)


# Exception types we consider transient — a second try has a real chance.
# Permanent errors (ToolError, ValueError, bad args) propagate immediately.
_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    BrokenPipeError,
)
try:  # httpx is always present (mcp depends on it), but fail gracefully
    import httpx as _httpx
    _TRANSIENT_EXCEPTIONS = (*_TRANSIENT_EXCEPTIONS, _httpx.TimeoutException, _httpx.NetworkError)
except ImportError:  # pragma: no cover
    pass


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
    async def _do_call_tool(self, name: str, arguments: dict | None) -> Any: ...

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """Audited + retried wrapper — records latency + status regardless
        of transport; retries once on transient transport errors.

        Concrete subclasses implement ``_do_call_tool``; never override
        ``call_tool`` directly or audit/retry will be bypassed.
        """
        return await measure(
            self._call_with_retry(name, arguments),
            tool_name=name, args=arguments,
        )

    async def _call_with_retry(self, name: str, arguments: dict | None) -> Any:
        """One-shot retry on transient errors — permanent errors propagate
        immediately. Second attempt uses a fresh attempt; we don't
        re-enter the transport context (the outer caller owns that)."""
        try:
            return await self._do_call_tool(name, arguments)
        except _TRANSIENT_EXCEPTIONS as e:
            logger.info("mcp_call_tool_retry", tool=name, error=str(e))
            return await self._do_call_tool(name, arguments)


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


# Backoff schedule for session establishment retries (seconds, indexed by
# failed-attempt count). Total attempts = max_attempts passed by caller.
RECONNECT_BACKOFF: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)


def is_transient_error(exc: BaseException) -> bool:
    """True if ``exc`` is worth retrying — i.e. a transport/network hiccup
    rather than a protocol / validation error."""
    return isinstance(exc, _TRANSIENT_EXCEPTIONS)


async def backoff_delay(attempt: int) -> None:
    """Sleep the backoff window after a failed ``attempt`` (0-indexed).
    Uses the last bucket past the table's end, so callers don't need to
    clamp themselves."""
    delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
    await asyncio.sleep(delay)
