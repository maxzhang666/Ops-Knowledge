import asyncio

import pytest

from app.workflow.events import Event, EventBus


@pytest.mark.asyncio
async def test_publish_fanout():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    await bus.publish(Event(type="node_start", execution_id="e"))
    assert (await q1.get()).type == "node_start"
    assert (await q2.get()).type == "node_start"


@pytest.mark.asyncio
async def test_close_emits_sentinel():
    bus = EventBus()
    q = bus.subscribe()
    await bus.close()
    # First item is the sentinel (None)
    assert await q.get() is None


@pytest.mark.asyncio
async def test_stream_iterator_terminates_on_close():
    bus = EventBus()
    q = bus.subscribe()

    async def _collect():
        return [ev.type async for ev in bus.stream(q)]

    task = asyncio.create_task(_collect())
    await bus.publish(Event(type="node_start", execution_id="e"))
    await bus.close()
    types = await task
    assert types == ["node_start"]


@pytest.mark.asyncio
async def test_non_critical_drops_when_full():
    bus = EventBus(queue_size=1)
    q = bus.subscribe()  # noqa: F841
    # Fill queue — second stream_chunk should be dropped, not block
    await bus.publish(Event(type="stream_chunk", execution_id="e", data={"delta": "a"}))
    await bus.publish(Event(type="stream_chunk", execution_id="e", data={"delta": "b"}))
    # Queue only holds the first; second was dropped.
    assert q.qsize() == 1
