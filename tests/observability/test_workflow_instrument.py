import asyncio

import pytest

from app.observability.workflow_instrument import attach_bus_instrumentation
from app.workflow.events import Event, EventBus


class _FakeSpan:
    def __init__(self, name, metadata=None):
        self.name = name
        self.metadata = metadata or {}
        self.updates: list[dict] = []
        self.ended = False

    def update(self, **kw):
        self.updates.append(kw)

    def end(self, **kw):
        self.ended = True


class _FakeTrace:
    def __init__(self):
        self.spans: list[_FakeSpan] = []

    def span(self, name=None, metadata=None):
        s = _FakeSpan(name, metadata)
        self.spans.append(s)
        return s


@pytest.mark.asyncio
async def test_node_lifecycle_spans():
    bus = EventBus()
    trace = _FakeTrace()
    task = attach_bus_instrumentation(bus, trace)

    await bus.publish(Event(type="node_start", execution_id="e", node_id="n1",
                            data={"type": "llm"}))
    await bus.publish(Event(type="node_output", execution_id="e", node_id="n1",
                            data={"outputs": {"content": "x"}, "token_usage": {"prompt_tokens": 5}}))
    await bus.publish(Event(type="node_end", execution_id="e", node_id="n1",
                            data={"status": "succeeded"}))
    await bus.close()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(trace.spans) == 1
    assert trace.spans[0].name == "node.llm"
    assert trace.spans[0].ended is True


@pytest.mark.asyncio
async def test_error_sets_error_level():
    bus = EventBus()
    trace = _FakeTrace()
    task = attach_bus_instrumentation(bus, trace)

    await bus.publish(Event(type="node_start", execution_id="e", node_id="n2",
                            data={"type": "code"}))
    await bus.publish(Event(type="node_error", execution_id="e", node_id="n2",
                            data={"error": "boom"}))
    await bus.publish(Event(type="node_end", execution_id="e", node_id="n2",
                            data={"status": "failed"}))
    await bus.close()
    await asyncio.wait_for(task, timeout=1.0)

    assert any(u.get("level") == "ERROR" for u in trace.spans[0].updates)
    assert trace.spans[0].ended is True


@pytest.mark.asyncio
async def test_stream_chunks_are_ignored():
    bus = EventBus()
    trace = _FakeTrace()
    task = attach_bus_instrumentation(bus, trace)

    await bus.publish(Event(type="stream_chunk", execution_id="e", node_id="x",
                            data={"delta": "a"}))
    await bus.publish(Event(type="workflow_start", execution_id="e"))
    await bus.publish(Event(type="workflow_end", execution_id="e", data={"status": "succeeded"}))
    await bus.close()
    await asyncio.wait_for(task, timeout=1.0)

    # No node_start came through → no spans created.
    assert trace.spans == []
