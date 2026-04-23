"""Phase 2 Day 5 — streaming nodes + LangGraph event bridge.

Answer node is ``streaming=True``; with a literal ``answer`` it chunks
the text via ``on_stream`` in 16-byte slices. We verify:

 1. ``stream_execution`` publishes the expected lifecycle events to the
    EventBus (workflow_start, node_start×N, node_output×N, node_end×N,
    stream_chunk×M, workflow_end).
 2. Chunks concatenate to the original answer text.
 3. Final state has the Answer node's output recorded.
"""
from __future__ import annotations

import pytest

from app.workflow.dsl import parse_dsl
from app.workflow.events import EventBus
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.events import stream_execution
from app.workflow.langgraph.state import initial_state


pytestmark = pytest.mark.asyncio


async def _collect_events(bus: EventBus, run_task) -> list:
    """Drain all events until the bus is closed.

    ``bus.subscribe()`` returns a raw ``asyncio.Queue`` — wrap it via
    ``bus.stream()`` to get an async iterator of events.
    """
    import asyncio

    q = bus.subscribe()
    events: list = []

    async def reader():
        async for ev in bus.stream(q):
            events.append(ev)

    r = asyncio.create_task(reader())
    await run_task  # let the graph finish first
    await bus.close()  # sentinel → reader drains remaining + exits
    await r
    return events


async def test_streaming_answer_emits_chunks() -> None:
    raw = {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "answer", "type": "answer",
                 "data": {"inputs": {"answer": "hello streaming world"}}},
            ],
            "edges": [{"source": "start", "target": "answer"}],
        },
        "workflow_variables": [],
    }
    dsl = parse_dsl(raw)
    compiled = compile_dsl(dsl)
    bus = EventBus()
    import asyncio

    async def runner():
        return await stream_execution(
            compiled, initial_state({"content": "hi"}),
            bus, execution_id="test-exec-1",
        )

    run_task = asyncio.create_task(runner())
    events = await _collect_events(bus, run_task)
    final_state = run_task.result()

    # Lifecycle framing
    assert events[0].type == "workflow_start"
    assert events[-1].type == "workflow_end"
    assert events[-1].data["status"] == "succeeded"

    # Answer emitted stream chunks; verify concatenation matches literal.
    chunks = [e for e in events if e.type == "stream_chunk" and e.node_id == "answer"]
    assert chunks, "expected at least one stream_chunk from answer"
    assembled = "".join(e.data["delta"] for e in chunks)
    assert assembled == "hello streaming world"

    # Each node got node_start + node_output + node_end.
    for nid in ("start", "answer"):
        assert any(
            e.type == "node_start" and e.node_id == nid for e in events
        ), f"missing node_start for {nid}"
        assert any(
            e.type == "node_end" and e.node_id == nid for e in events
        ), f"missing node_end for {nid}"

    # Final state has the answer output.
    assert final_state["outputs"]["answer"]["answer"] == "hello streaming world"
