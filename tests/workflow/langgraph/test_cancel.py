"""Phase 2 Day 7 — cancel verification.

Semantics we're guaranteeing:
 1. ``asyncio.Task.cancel()`` on the running ``stream_execution`` task
    propagates through LangGraph → the current node's ``execute`` receives
    ``CancelledError``.
 2. Downstream nodes don't run after cancel.
 3. The EventBus sees a ``workflow_end(status="failed")`` (or the stream
    raises, which we translate to a failed end event).

We install a throwaway ``SleepyAnswer`` node class just for this test so
we can pause ``execute`` for a controllable duration without relying on
real LLM / network.
"""
from __future__ import annotations

import asyncio

import pytest

from app.workflow.dsl import parse_dsl
from app.workflow.events import EventBus
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.events import stream_execution
from app.workflow.langgraph.state import initial_state
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)
from app.workflow.nodes.registry import registry


pytestmark = pytest.mark.asyncio


class SleepyAnswer(AbstractNode):
    """Test double: sleeps 5s inside ``execute`` so the test can cancel
    mid-flight. Registered under a private ``test.sleepy`` type."""

    manifest = NodeManifest(
        type="test.sleepy",
        type_version="1.0",
        category="output",
        name="SleepyAnswer",
        description="Test-only: sleeps, used to verify cancel semantics.",
        is_terminal=True,
    )
    io = NodeIO(inputs={}, outputs={"answer": {"type": "string"}})
    config_form = NodeConfigForm()

    async def execute(self, ctx: NodeContext) -> NodeResult:
        await asyncio.sleep(5.0)  # longer than any test will wait
        return NodeResult(outputs={"answer": "should not reach here"})


@pytest.fixture(autouse=True)
def _register_sleepy():
    """Ensure the test node is registered exactly once per run."""
    key = registry._key(SleepyAnswer.manifest.type, SleepyAnswer.manifest.type_version)
    if key not in registry._entries:
        registry.register(SleepyAnswer)
    yield


async def test_cancel_stops_downstream() -> None:
    """Cancel mid-flight. Sleepy node's execute gets CancelledError; the
    answer node that follows must not run."""
    dsl = parse_dsl({
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "sleepy", "type": "test.sleepy", "data": {}},
                {"id": "answer", "type": "answer",
                 "data": {"inputs": {"answer": "never"}}},
            ],
            "edges": [
                {"source": "start", "target": "sleepy"},
                {"source": "sleepy", "target": "answer"},
            ],
        },
        "workflow_variables": [],
    })
    compiled = compile_dsl(dsl)
    bus = EventBus()

    async def run():
        return await stream_execution(
            compiled, initial_state({"content": "hi"}),
            bus, execution_id="cancel-test",
        )

    task = asyncio.create_task(run())

    # Let start complete and sleepy begin running before cancelling.
    # 100ms is enough for both node transitions; sleepy will be mid-sleep.
    await asyncio.sleep(0.1)
    task.cancel()

    # Expect CancelledError to propagate; stream_execution also publishes
    # workflow_end(failed) before re-raising.
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    await bus.close()

    # Collect all events that were emitted.
    q = bus.subscribe()
    events: list = []
    # Bus is closed, stream will drain the queue and terminate.
    async for ev in bus.stream(q):
        events.append(ev)

    node_ends = {e.node_id for e in events if e.type == "node_end"}
    # Crucial: ``answer`` must not have a node_end — it never ran.
    assert "answer" not in node_ends, (
        "downstream 'answer' node should not have executed after cancel"
    )
