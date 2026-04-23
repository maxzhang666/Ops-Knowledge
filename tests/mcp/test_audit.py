"""Audit pipeline — ContextVar propagation + measure() row writes.

We stub ``record_call`` so the tests don't need a real DB. Goal is
verifying the contract around ``measure``: it captures latency, labels
status 'ok'/'error', and re-raises after recording errors.
"""
from __future__ import annotations

import asyncio

import pytest

from app.mcp import audit
from app.mcp.audit import CallContext, call_context, measure, use_call_context


@pytest.fixture(autouse=True)
def _capture_calls(monkeypatch):
    """Replace ``record_call`` with an in-memory list recorder."""
    records: list[dict] = []

    async def _rec(**kw):
        records.append(kw)

    monkeypatch.setattr(audit, "record_call", _rec)
    return records


@pytest.mark.asyncio
async def test_measure_ok_records_latency_and_result(_capture_calls):
    async def work():
        await asyncio.sleep(0.01)
        return "value"

    out = await measure(work(), tool_name="t", args={"a": 1})

    assert out == "value"
    assert len(_capture_calls) == 1
    rec = _capture_calls[0]
    assert rec["tool_name"] == "t"
    assert rec["status"] == "ok"
    assert rec["args"] == {"a": 1}
    assert rec["latency_ms"] is not None and rec["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_measure_error_records_and_reraises(_capture_calls):
    async def work():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await measure(work(), tool_name="t", args=None)

    assert len(_capture_calls) == 1
    rec = _capture_calls[0]
    assert rec["status"] == "error"
    assert rec["error"] == "boom"
    assert rec["result"] is None


@pytest.mark.asyncio
async def test_use_call_context_scope():
    """ContextVar must be reset when the async with block exits."""
    import uuid
    assert call_context.get() is None
    ctx = CallContext(server_id=uuid.uuid4(), agent_id=uuid.uuid4())
    async with use_call_context(ctx):
        assert call_context.get() is ctx
    assert call_context.get() is None


@pytest.mark.asyncio
async def test_use_call_context_nested():
    import uuid
    outer = CallContext(server_id=uuid.uuid4())
    inner = CallContext(server_id=uuid.uuid4())
    async with use_call_context(outer):
        assert call_context.get() is outer
        async with use_call_context(inner):
            assert call_context.get() is inner
        assert call_context.get() is outer
    assert call_context.get() is None
