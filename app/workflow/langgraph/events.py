"""Bridge LangGraph's ``astream(stream_mode=["updates", "custom"])`` output
to our ``EventBus``.

Design:
- ``updates`` mode: emitted once per node after it completes, with the
  dict the node returned. We translate this into ``node_output`` +
  ``node_end`` events (and ``node_start`` synthesised just before,
  since LangGraph doesn't have a separate start event for node callables).
- ``custom`` mode: emitted whenever a node calls ``StreamWriter``. Our
  ``streaming.write_chunk`` puts a payload of shape
  ``{"kind": "stream_chunk", "node_id", "delta", "meta"}`` — one ``stream_chunk``
  Event per.
- Graph completion → ``workflow_end``.
- Any exception from ``astream`` → ``workflow_end(status="failed")``.

The frontend consumes the existing EventBus protocol unchanged. This
module is the only translation layer.
"""
from __future__ import annotations

import logging
from typing import Any

from app.workflow.events import Event, EventBus

log = logging.getLogger(__name__)


async def stream_execution(
    compiled,
    initial: dict[str, Any] | None,
    bus: EventBus,
    execution_id: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run ``compiled.astream`` and relay events to ``bus``; return final state.

    ``bus.close()`` is NOT called here — the caller owns the lifecycle.

    ``thread_id``: pass through to LangGraph so a checkpointer (if compiled
    in) scopes state to this thread. For one-shot runs, ``thread_id ==
    execution_id``. For Workflow Agent multi-turn, pass the conversation id
    so successive turns share checkpointed state. None → no checkpointing
    scope (checkpointer will still run if compiled in, using a default).
    """
    await bus.publish(Event(
        type="workflow_start",
        execution_id=execution_id,
        data={"engine": "langgraph"},
    ))

    final_state: dict[str, Any] = {}
    started: set[str] = set()

    # LangGraph requires ``thread_id`` in the config whenever a checkpointer
    # is compiled in. Pass the caller-supplied value (or execution_id as a
    # safe default).
    config = {
        "configurable": {
            "thread_id": thread_id or execution_id,
        },
    }

    # ``initial`` may be:
    #   - a WorkflowState dict for a new run
    #   - a ``Command(resume=value)`` to continue a paused (HITL) run
    #   - None when only resuming from the last checkpoint (rare)
    # Buffer interrupts captured via the updates stream — if non-empty at the
    # end, we emit ``waiting_input`` without needing ``aget_state``.
    pending_interrupts: list[dict[str, Any]] = []

    try:
        async for mode, payload in compiled.astream(
            initial, config=config, stream_mode=["updates", "custom"],
        ):
            if mode == "updates":
                # payload: {node_id: <state_delta>} + optional meta keys like
                # ``__interrupt__`` (tuple of Interrupt) / ``__metadata__``.
                for node_id, delta in (payload or {}).items():
                    if node_id == "__interrupt__":
                        # Interrupt signal — LangGraph will halt right after
                        # this chunk. Collect the Interrupt payloads so we
                        # can emit ``waiting_input``.
                        for itr in (delta or ()):
                            val = getattr(itr, "value", None) if not isinstance(itr, dict) else itr.get("value")
                            itr_id = getattr(itr, "id", None) if not isinstance(itr, dict) else itr.get("id")
                            if val is not None:
                                pending_interrupts.append({"id": itr_id, "value": val})
                        continue
                    if node_id.startswith("__"):
                        # Other internal keys (__metadata__, __end__) — skip.
                        continue
                    if not isinstance(delta, dict):
                        # Defensive: any future meta key we don't recognise.
                        continue
                    await _emit_node_lifecycle(
                        bus, execution_id, node_id, delta, started,
                    )
                    _merge_into(final_state, delta)
            elif mode == "custom":
                # payload from write_chunk: {kind, node_id, delta, meta}
                if isinstance(payload, dict) and payload.get("kind") == "stream_chunk":
                    await bus.publish(Event(
                        type="stream_chunk",
                        execution_id=execution_id,
                        node_id=payload.get("node_id"),
                        data={
                            "delta": payload.get("delta", ""),
                            "meta": payload.get("meta"),
                        },
                    ))

        # When a checkpointer is present, prefer the full checkpointed state
        # over our update-stream accumulation. Required for resume flows:
        # ``astream`` from a ``Command(resume=...)`` only emits deltas for
        # nodes that ran THIS pass, so the accumulator would lose state
        # written in the pre-interrupt run.
        has_checkpointer = getattr(compiled, "checkpointer", None) is not None
        if has_checkpointer:
            try:
                snapshot = await compiled.aget_state(config)
                values = snapshot.values or {}
                # Merge snapshot on top of stream-accumulated state so we get
                # the union (covers edge cases where stream saw something
                # checkpoint persist hasn't flushed yet).
                for k, v in values.items():
                    if isinstance(v, dict) and isinstance(final_state.get(k), dict):
                        merged = dict(final_state[k])
                        merged.update(v)
                        final_state[k] = merged
                    else:
                        final_state[k] = v
            except Exception:  # noqa: BLE001
                log.warning("aget_state_failed exec=%s", execution_id, exc_info=True)

        # If we collected ``__interrupt__`` signals during the stream, the
        # graph paused for HITL. Emit ``waiting_input`` + ``workflow_end(
        # status="waiting")`` instead of a normal success end.
        interrupts = pending_interrupts
        if interrupts:
            await bus.publish(Event(
                type="waiting_input",
                execution_id=execution_id,
                data={"interrupts": interrupts, "thread_id": config["configurable"]["thread_id"]},
            ))
            await bus.publish(Event(
                type="workflow_end",
                execution_id=execution_id,
                data={"status": "waiting"},
            ))
            final_state["_status"] = "waiting"
            final_state["_interrupts"] = interrupts
            return final_state

        await bus.publish(Event(
            type="workflow_end",
            execution_id=execution_id,
            data={"status": "succeeded"},
        ))
    except Exception as e:  # noqa: BLE001
        log.exception("LangGraph execution %s failed", execution_id)
        await bus.publish(Event(
            type="workflow_end",
            execution_id=execution_id,
            data={"status": "failed", "error": str(e)},
        ))
        raise

    return final_state


async def _emit_node_lifecycle(
    bus: EventBus,
    execution_id: str,
    node_id: str,
    delta: dict[str, Any],
    started: set[str],
) -> None:
    """LangGraph ``updates`` arrives only after a node returns. To preserve
    the existing ``node_start → node_output → node_end`` triptych the
    frontend expects, emit ``node_start`` synthetically right before
    ``node_output`` if we haven't already emitted it for this node.

    (In a future enhancement we could emit ``node_start`` from inside the
    adapter itself, giving the UI a real "running" state before execute
    finishes. Phase 2 MVP accepts the slightly-batched timing.)
    """
    if node_id not in started:
        started.add(node_id)
        # We don't know node_type without a lookup; omit for now — the
        # frontend uses node_id to correlate with canvas.
        await bus.publish(Event(
            type="node_start",
            execution_id=execution_id,
            node_id=node_id,
            data={},
        ))

    outputs = (delta.get("outputs") or {}).get(node_id, {})
    inputs = (delta.get("inputs") or {}).get(node_id, {})

    await bus.publish(Event(
        type="node_output",
        execution_id=execution_id,
        node_id=node_id,
        data={"outputs": outputs, "inputs": inputs},
    ))
    await bus.publish(Event(
        type="node_end",
        execution_id=execution_id,
        node_id=node_id,
        data={"status": "succeeded"},
    ))


def _merge_into(acc: dict[str, Any], delta: dict[str, Any]) -> None:
    """Shallow-merge a state delta (dict of node-bucket dicts) into the
    accumulator. Follows the same reducer semantics as ``state.merge_by_node``
    but at the top level of the delta."""
    for key, value in (delta or {}).items():
        existing = acc.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged = dict(existing)
            merged.update(value)
            acc[key] = merged
        else:
            acc[key] = value
