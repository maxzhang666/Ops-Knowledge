"""MCPServerService — CRUD + connectivity + tool discovery.

Connectivity / discovery helpers are guarded by an ``asyncio.wait_for``
so an unresponsive MCP server can't hold a request indefinitely. Errors
are surfaced as structured results (``ok=False, detail=...``) rather
than raising — the admin UI needs to render the failure reason.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.mcp.audit import CallContext, use_call_context
from app.mcp.models import MCPServer, MCPToolCall
from app.mcp.schemas import (
    MCPServerCreate,
    MCPServerUpdate,
    MCPTool,
    TestConnectionResult,
)
from app.mcp.transports import get_transport
from app.mcp.transports.base import backoff_delay, is_transient_error

logger = structlog.get_logger(__name__)

CONNECT_TIMEOUT = 15  # seconds — covers handshake + list_tools for slow servers
MAX_CONNECT_ATTEMPTS = 3  # including first try; used by test_connection + discover_tools


class MCPServerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────────

    async def create_server(
        self, data: MCPServerCreate, created_by: uuid.UUID | None,
    ) -> MCPServer:
        server = MCPServer(
            name=data.name,
            description=data.description,
            transport_type=data.transport_type,
            config=data.config,
            auth_config=data.auth_config.model_dump(exclude_none=True) if data.auth_config else None,
            enabled_tools=data.enabled_tools,
            is_active=data.is_active,
            created_by=created_by,
        )
        self.db.add(server)
        await self.db.flush()
        await self.db.refresh(server)
        return server

    async def list_servers(self, active_only: bool = False) -> list[MCPServer]:
        stmt = select(MCPServer).order_by(MCPServer.created_at.desc())
        if active_only:
            stmt = stmt.where(MCPServer.is_active.is_(True))
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def get_server(self, server_id: uuid.UUID) -> MCPServer:
        server = await self.db.get(MCPServer, server_id)
        if server is None:
            raise NotFoundError("MCPServer", str(server_id))
        return server

    async def update_server(
        self, server_id: uuid.UUID, data: MCPServerUpdate,
    ) -> MCPServer:
        server = await self.get_server(server_id)
        payload = data.model_dump(exclude_unset=True)
        # AuthConfig is already model-dumped by Pydantic; coerce sub-model if present
        if "auth_config" in payload and data.auth_config is not None:
            payload["auth_config"] = data.auth_config.model_dump(exclude_none=True)
        for key, value in payload.items():
            setattr(server, key, value)
        await self.db.flush()
        await self.db.refresh(server)
        return server

    async def delete_server(self, server_id: uuid.UUID) -> None:
        server = await self.get_server(server_id)
        await self.db.delete(server)
        await self.db.flush()

    # ── Connectivity & discovery ─────────────────────────────────

    async def test_connection(self, server_id: uuid.UUID) -> TestConnectionResult:
        server = await self.get_server(server_id)

        async def _do() -> dict:
            async with get_transport(server) as t:
                return await t.initialize()

        try:
            info = await _open_with_retry(_do)
        except asyncio.TimeoutError:
            await self._mark_health(server, "unreachable")
            return TestConnectionResult(ok=False, detail=f"handshake timed out ({CONNECT_TIMEOUT}s)")
        except Exception as exc:  # noqa: BLE001
            await self._mark_health(server, "degraded")
            return TestConnectionResult(ok=False, detail=str(exc)[:500])
        await self._mark_health(server, "ok")
        return TestConnectionResult(ok=True, detail="handshake succeeded", server_info=info)

    async def discover_tools(self, server_id: uuid.UUID) -> list[MCPTool]:
        server = await self.get_server(server_id)

        async def _do() -> list[MCPTool]:
            async with get_transport(server) as t:
                await t.initialize()
                return await t.list_tools()

        try:
            tools = await _open_with_retry(_do)
        except asyncio.TimeoutError:
            await self._mark_health(server, "unreachable")
            raise ValueError(f"discovery timed out ({CONNECT_TIMEOUT}s)")
        except Exception as exc:  # noqa: BLE001
            await self._mark_health(server, "degraded")
            raise ValueError(str(exc)[:500])

        server.discovered_tools = [t.model_dump() for t in tools]
        await self._mark_health(server, "ok")
        await self.db.flush()
        return tools

    async def get_tools(self, server_id: uuid.UUID) -> list[MCPTool]:
        """Return cached tool list; auto-discover if never populated.

        ``enabled_tools`` whitelist is applied here so Agents only see the
        tools an admin explicitly exposed.
        """
        server = await self.get_server(server_id)
        if not server.discovered_tools:
            tools = await self.discover_tools(server_id)
        else:
            tools = [MCPTool(**t) for t in server.discovered_tools]
        allowed = server.enabled_tools
        if allowed is None:
            return tools
        allowed_set = set(allowed)
        return [t for t in tools if t.name in allowed_set]

    # ── Audit log query ──────────────────────────────────────────

    async def list_tool_calls(
        self,
        server_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[MCPToolCall]:
        """Recent-first audit rows. Admin-only in the router."""
        stmt = select(MCPToolCall).order_by(desc(MCPToolCall.called_at)).limit(
            max(1, min(limit, 500))
        )
        if server_id is not None:
            stmt = stmt.where(MCPToolCall.mcp_server_id == server_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    # ── Internal helpers ─────────────────────────────────────────

    async def _mark_health(self, server: MCPServer, status: str) -> None:
        server.health_status = status
        server.last_checked_at = datetime.now(timezone.utc)
        await self.db.flush()


async def _open_with_retry(do):
    """Exponential-backoff wrapper for connection-sensitive MCP ops.

    Each attempt is individually capped at ``CONNECT_TIMEOUT``; backoff
    runs only between transient failures. Permanent errors (ValueError,
    bad config, auth rejection) propagate on the first try.
    """
    last_exc: BaseException | None = None
    for attempt in range(MAX_CONNECT_ATTEMPTS):
        try:
            return await asyncio.wait_for(do(), timeout=CONNECT_TIMEOUT)
        except asyncio.TimeoutError as e:
            last_exc = e
        except Exception as e:  # noqa: BLE001
            if is_transient_error(e):
                last_exc = e
            else:
                raise
        if attempt < MAX_CONNECT_ATTEMPTS - 1:
            await backoff_delay(attempt)
    assert last_exc is not None
    raise last_exc
