"""Adapt our ``AbstractNode`` subclasses into LangGraph-compatible callables.

A node function signature in LangGraph is::

    async def node_fn(state: WorkflowState) -> dict

Returning a partial state dict that LangGraph merges back via the reducers
declared in ``state.py``.

This adapter handles the boring-but-essential wiring:
 1. Reconstruct a ``NodeContext`` with **resolved inputs** from the global
    state. Selector arrays look up upstream outputs; template strings are
    resolved via a lightweight ``ExecutionContext`` built from the current
    state snapshot; literals pass through.
 2. Invoke ``AbstractNode.validate`` and ``AbstractNode.execute``.
 3. Convert the ``NodeResult`` back into a state update.

Streaming (``on_stream``) is Phase 2 Day 5. Error-handling modes (retry /
default-value / fail-branch) are Phase 3.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from app.workflow.context import ExecutionContext
from app.workflow.dsl import NodeDef
from app.workflow.nodes.base import AbstractNode, NodeContext, NodeResult
from app.workflow.nodes.registry import registry

from .state import WorkflowState
from .streaming import write_chunk


NodeFn = Callable[[WorkflowState], Awaitable[dict[str, Any]]]

log = logging.getLogger(__name__)

# Grace window (seconds) after execute() returns before we cancel a
# still-running on_stream pump. Mirrors the legacy scheduler setting.
_STREAM_DRAIN_TIMEOUT = 2.0


def build_node_adapter(node_def: NodeDef) -> NodeFn:
    """Factory: produce a LangGraph node callable for a DSL node.

    The returned function captures ``node_def`` and on each invocation:
    looks up the ``AbstractNode`` class from the registry, resolves
    inputs, runs validate/execute, and returns the state delta.
    """

    node_cls = registry.get(node_def.type, node_def.type_version)

    async def adapter(state: WorkflowState) -> dict[str, Any]:
        instance: AbstractNode = node_cls()

        # Rebuild an ExecutionContext from the snapshot of the current state
        # so the node's existing selector/template resolution code just works.
        exec_ctx = _execution_context_from_state(state)

        # Resolve declared inputs from ``node_def.data["inputs"]``.
        resolved_inputs = _resolve_inputs(node_def, instance, exec_ctx)

        # Compound nodes (iteration / loop) carry ``blocks`` + ``block_edges``
        # at the NodeDef top level; surface them in ``ctx.config`` so the
        # node's execute() finds the sub-graph.
        node_config = dict(node_def.data or {})
        if node_def.blocks is not None:
            node_config["blocks"] = [b.model_dump() for b in node_def.blocks]
        if node_def.block_edges is not None:
            node_config["block_edges"] = [e.model_dump() for e in node_def.block_edges]

        node_ctx = NodeContext(
            node_id=node_def.id,
            node_type=node_def.type,
            inputs=resolved_inputs,
            config=node_config,
            execution_context=exec_ctx,
        )

        await instance.validate(node_ctx)

        if getattr(instance, "manifest", None) and instance.manifest.streaming:
            result = await _run_with_streaming(instance, node_ctx, node_def.id)
        else:
            result = await instance.execute(node_ctx)

        return {
            "inputs": {node_def.id: dict(resolved_inputs)},
            "outputs": {node_def.id: dict(result.outputs)},
            "branches": {node_def.id: result.branch},
        }

    adapter.__name__ = f"adapter__{node_def.id}"
    return adapter


def _execution_context_from_state(state: WorkflowState) -> ExecutionContext:
    """Build an ``ExecutionContext`` that mirrors what the legacy scheduler
    would pass in. Upstream outputs come from ``state.outputs``; trigger
    input is surfaced as ``vars.trigger`` (unchanged semantics)."""
    ctx = ExecutionContext(
        workflow_variables=state.get("workflow_variables", {}),
        trigger_input=state.get("trigger_input"),
    )
    for node_id, output in (state.get("outputs") or {}).items():
        ctx.record_output(node_id, output)
    return ctx


async def _run_with_streaming(
    instance: AbstractNode,
    node_ctx: NodeContext,
    node_id: str,
) -> NodeResult:
    """Run a streaming-capable node: pump ``on_stream`` concurrently with
    ``execute``. Chunks go into LangGraph's custom stream via ``write_chunk``.

    Mirrors the legacy scheduler's ``_execute_with_streaming`` semantics —
    pump starts first, we ``sleep(0)`` to let it tick, then ``execute`` runs;
    after execute returns we give the pump a short grace window to drain
    before cancelling. This matters for Answer-style nodes where execute()
    is synchronous and would otherwise return before on_stream gets scheduled.
    """

    async def _pump() -> None:
        try:
            async for chunk in instance.on_stream(node_ctx):
                write_chunk(node_id, chunk.delta, chunk.meta)
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001
            log.warning("Stream pump failed for %s: %s", node_id, e)

    stream_task = asyncio.create_task(_pump())
    # Let the pump get scheduled before execute() potentially returns
    # synchronously (e.g. Answer with a literal input).
    await asyncio.sleep(0)
    try:
        result = await instance.execute(node_ctx)
    finally:
        try:
            await asyncio.wait_for(stream_task, timeout=_STREAM_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            stream_task.cancel()
            try:
                await stream_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
    return result


def _resolve_inputs(
    node_def: NodeDef,
    instance: AbstractNode,
    exec_ctx: ExecutionContext,
) -> dict[str, Any]:
    """Resolve each declared ``io.inputs`` key from ``node_def.data["inputs"]``."""
    resolved: dict[str, Any] = {}
    raw_inputs: dict[str, Any] = {}
    if isinstance(node_def.data, dict):
        raw_inputs = node_def.data.get("inputs", {}) or {}

    for input_name in (instance.io.inputs or {}):
        ref = raw_inputs.get(input_name)
        if isinstance(ref, list):
            resolved[input_name] = exec_ctx.resolve_selector(ref)
        elif isinstance(ref, str):
            resolved[input_name] = exec_ctx.resolve_template(ref)
        elif ref is not None:
            resolved[input_name] = ref
    return resolved
