"""MCP health-check Celery task (Plan 30 M3.2) — exercise the async core.

Shallow coverage of transitions and the notification hook; we mock the
transport + session factory so no Postgres / MCP server is needed.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.mcp import tasks as mcp_tasks
from app.mcp.transports.base import MCPTransport


class _StubTransport(MCPTransport):
    def __init__(self, *, raise_on_init: Exception | None = None):
        self._raise = raise_on_init

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def initialize(self):
        if self._raise:
            raise self._raise
        return {"name": "stub"}

    async def list_tools(self):
        return []

    async def _do_call_tool(self, name, arguments):
        return None


def _fake_server(name="s1", prev_health=None):
    s = SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        is_active=True,
        transport_type="http",
        config={"url": "https://x/mcp"},
        auth_config=None,
        health_status=prev_health,
        last_checked_at=None,
    )
    return s


class _FakeDB:
    """Just enough surface for _run_health_check — execute/commit/flush/add."""

    def __init__(self, servers):
        self.servers = servers
        self.notifications: list = []
        self.commits = 0

    async def execute(self, _stmt):
        class _Scalars:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def all(self):
                return self._rows
        return _Scalars(self.servers)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    def add(self, obj):
        self.notifications.append(obj)


@pytest.fixture
def _patch_env(monkeypatch):
    """Swap out the async engine + sessionmaker for a fake DB holder."""
    def _apply(servers, transport_behavior):
        fake_db = _FakeDB(servers)

        @asynccontextmanager
        async def fake_session():
            yield fake_db

        class _SessionMaker:
            def __call__(self):
                return fake_session()

        class _Engine:
            async def dispose(self):
                pass

        monkeypatch.setattr(mcp_tasks, "create_async_engine", lambda *a, **kw: _Engine())
        monkeypatch.setattr(mcp_tasks, "async_sessionmaker", lambda *a, **kw: _SessionMaker())

        def _get_transport_stub(server):
            return transport_behavior(server)

        monkeypatch.setattr(mcp_tasks, "get_transport", _get_transport_stub)
        return fake_db

    return _apply


@pytest.mark.asyncio
async def test_all_healthy(_patch_env):
    servers = [_fake_server("a", prev_health="ok"), _fake_server("b")]
    fake_db = _patch_env(servers, lambda s: _StubTransport())
    out = await mcp_tasks._run_health_check()
    assert out == {"ok": 2, "unreachable": 0, "newly_failed": 0}
    assert all(s.health_status == "ok" for s in servers)
    assert fake_db.notifications == []


@pytest.mark.asyncio
async def test_transition_ok_to_unreachable_triggers_notification(_patch_env):
    """A server that was healthy but now times out must notify admins."""
    server = _fake_server("flaky", prev_health="ok")
    fake_db = _patch_env(
        [server],
        lambda s: _StubTransport(raise_on_init=asyncio.TimeoutError()),
    )
    out = await mcp_tasks._run_health_check()
    assert out["unreachable"] == 1
    assert out["newly_failed"] == 1
    assert server.health_status == "unreachable"
    assert len(fake_db.notifications) == 1
    notif = fake_db.notifications[0]
    assert notif.type == "system"
    assert notif.priority == "high"


@pytest.mark.asyncio
async def test_already_unhealthy_no_duplicate_notification(_patch_env):
    """No re-notify if the server was already known-bad."""
    server = _fake_server("still-down", prev_health="unreachable")
    fake_db = _patch_env(
        [server],
        lambda s: _StubTransport(raise_on_init=asyncio.TimeoutError()),
    )
    out = await mcp_tasks._run_health_check()
    assert out["newly_failed"] == 0
    assert fake_db.notifications == []


@pytest.mark.asyncio
async def test_non_timeout_error_marks_degraded(_patch_env):
    """Arbitrary exceptions (not timeout) → 'degraded', not 'unreachable'."""
    server = _fake_server("weird")
    _patch_env(
        [server],
        lambda s: _StubTransport(raise_on_init=RuntimeError("bad protocol")),
    )
    await mcp_tasks._run_health_check()
    assert server.health_status == "degraded"
