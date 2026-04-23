"""Transport retry + backoff helpers (Plan 30 M3.3)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.mcp import audit
from app.mcp.transports.base import (
    RECONNECT_BACKOFF,
    backoff_delay,
    is_transient_error,
)
from app.mcp.transports.http import StreamableHTTPTransport


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    async def _noop(**_):
        pass
    monkeypatch.setattr(audit, "record_call", _noop)


def test_is_transient_error_recognizes_timeout():
    assert is_transient_error(asyncio.TimeoutError())


def test_is_transient_error_recognizes_connection_errors():
    assert is_transient_error(ConnectionError("reset"))
    assert is_transient_error(BrokenPipeError())


def test_is_transient_error_rejects_permanent():
    assert not is_transient_error(ValueError("bad args"))
    assert not is_transient_error(RuntimeError("boom"))


@pytest.mark.asyncio
async def test_backoff_delay_clamps_to_last_bucket(monkeypatch):
    """Attempts past the table's end should still sleep (clamp to last entry)."""
    slept: list[float] = []

    async def _fake_sleep(t):
        slept.append(t)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    # Past the end of RECONNECT_BACKOFF still returns the last value
    await backoff_delay(len(RECONNECT_BACKOFF) + 10)
    assert slept == [RECONNECT_BACKOFF[-1]]


@pytest.mark.asyncio
async def test_call_tool_retries_once_on_transient():
    """``call_tool`` must retry exactly once on TimeoutError."""
    t = StreamableHTTPTransport({"url": "https://x/mcp"}, {})
    attempts = {"n": 0}

    async def flaky(name, args):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise asyncio.TimeoutError()
        return "ok-on-retry"

    t._do_call_tool = flaky  # type: ignore[method-assign]
    result = await t.call_tool("x", {})
    assert result == "ok-on-retry"
    assert attempts["n"] == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_call_tool_does_not_retry_on_permanent():
    t = StreamableHTTPTransport({"url": "https://x/mcp"}, {})
    attempts = {"n": 0}

    async def bad(name, args):
        attempts["n"] += 1
        raise ValueError("bad args")

    t._do_call_tool = bad  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="bad args"):
        await t.call_tool("x", {})
    assert attempts["n"] == 1  # no retry


@pytest.mark.asyncio
async def test_call_tool_gives_up_after_one_retry():
    """Transient error on both attempts → re-raise the last one."""
    t = StreamableHTTPTransport({"url": "https://x/mcp"}, {})

    async def always_times_out(name, args):
        raise asyncio.TimeoutError()

    t._do_call_tool = always_times_out  # type: ignore[method-assign]
    with pytest.raises(asyncio.TimeoutError):
        await t.call_tool("x", {})
