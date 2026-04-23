"""Service-level behavior with a stubbed transport.

We patch ``app.mcp.service.get_transport`` to avoid spinning up real MCP
servers; instead a fake transport asserts the service layer's contract:
``test_connection`` updates health, ``discover_tools`` caches results,
``get_tools`` applies the ``enabled_tools`` whitelist.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.mcp.schemas import MCPTool


class _FakeTransport:
    """In-memory MCPTransport stand-in."""

    def __init__(self, tools: list[MCPTool], *, raise_on: str | None = None):
        self._tools = tools
        self._raise_on = raise_on

    async def __aenter__(self):
        if self._raise_on == "connect":
            raise RuntimeError("connection refused")
        return self

    async def __aexit__(self, *exc):
        return None

    async def initialize(self):
        if self._raise_on == "init":
            raise RuntimeError("handshake failed")
        return {"name": "fake", "version": "0", "protocol_version": "2024-11"}

    async def list_tools(self):
        if self._raise_on == "list":
            raise RuntimeError("list failed")
        return self._tools

    async def call_tool(self, name, arguments=None):
        return {"name": name, "args": arguments}


class _FakeServer:
    """Mutable dummy standing in for the ORM object — avoids needing a DB."""

    def __init__(self, **kw):
        self.id = kw.get("id", "server-1")
        self.transport_type = kw.get("transport_type", "http")
        self.config = kw.get("config", {"url": "https://x/mcp"})
        self.auth_config = kw.get("auth_config")
        self.enabled_tools = kw.get("enabled_tools")
        self.discovered_tools = kw.get("discovered_tools")
        self.health_status = kw.get("health_status")
        self.last_checked_at = None


class _FakeDB:
    """Minimal session surface used by the service (``get`` + ``flush``)."""

    def __init__(self, server):
        self._server = server
        self.flushed = 0

    async def get(self, _model, _id):
        return self._server

    async def flush(self):
        self.flushed += 1


def _patch_transport(monkeypatch, fake: _FakeTransport):
    @asynccontextmanager
    async def _factory(server):
        async with fake as t:
            yield t

    # service.py imports get_transport from transports; patch via service name
    import app.mcp.service as svc_mod

    def _mock_get_transport(server):
        return fake

    monkeypatch.setattr(svc_mod, "get_transport", _mock_get_transport)


@pytest.mark.asyncio
async def test_test_connection_success(monkeypatch):
    from app.mcp.service import MCPServerService

    server = _FakeServer()
    db = _FakeDB(server)
    svc = MCPServerService(db)

    _patch_transport(monkeypatch, _FakeTransport(tools=[]))
    result = await svc.test_connection(server.id)
    assert result.ok is True
    assert result.server_info == {"name": "fake", "version": "0", "protocol_version": "2024-11"}
    assert server.health_status == "ok"


@pytest.mark.asyncio
async def test_test_connection_failure_marks_degraded(monkeypatch):
    from app.mcp.service import MCPServerService

    server = _FakeServer()
    db = _FakeDB(server)
    svc = MCPServerService(db)

    _patch_transport(monkeypatch, _FakeTransport(tools=[], raise_on="init"))
    result = await svc.test_connection(server.id)
    assert result.ok is False
    assert server.health_status == "degraded"


@pytest.mark.asyncio
async def test_discover_tools_caches(monkeypatch):
    from app.mcp.service import MCPServerService

    tools = [MCPTool(name="a"), MCPTool(name="b")]
    server = _FakeServer()
    db = _FakeDB(server)
    svc = MCPServerService(db)

    _patch_transport(monkeypatch, _FakeTransport(tools=tools))
    got = await svc.discover_tools(server.id)
    assert [t.name for t in got] == ["a", "b"]
    assert server.discovered_tools == [
        {"name": "a", "description": None, "input_schema": None},
        {"name": "b", "description": None, "input_schema": None},
    ]
    assert server.health_status == "ok"


@pytest.mark.asyncio
async def test_get_tools_respects_whitelist(monkeypatch):
    from app.mcp.service import MCPServerService

    server = _FakeServer(
        discovered_tools=[
            {"name": "a", "description": None, "input_schema": None},
            {"name": "b", "description": None, "input_schema": None},
            {"name": "c", "description": None, "input_schema": None},
        ],
        enabled_tools=["a", "c"],
    )
    db = _FakeDB(server)
    svc = MCPServerService(db)

    got = await svc.get_tools(server.id)
    assert [t.name for t in got] == ["a", "c"]


@pytest.mark.asyncio
async def test_get_tools_null_whitelist_returns_all(monkeypatch):
    from app.mcp.service import MCPServerService

    server = _FakeServer(
        discovered_tools=[
            {"name": "a", "description": None, "input_schema": None},
            {"name": "b", "description": None, "input_schema": None},
        ],
        enabled_tools=None,
    )
    db = _FakeDB(server)
    svc = MCPServerService(db)

    got = await svc.get_tools(server.id)
    assert {t.name for t in got} == {"a", "b"}


@pytest.mark.asyncio
async def test_get_tools_empty_whitelist_returns_none(monkeypatch):
    from app.mcp.service import MCPServerService

    server = _FakeServer(
        discovered_tools=[{"name": "a", "description": None, "input_schema": None}],
        enabled_tools=[],
    )
    db = _FakeDB(server)
    svc = MCPServerService(db)

    got = await svc.get_tools(server.id)
    assert got == []
