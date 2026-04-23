"""LangGraph ``WorkflowState`` — the global state dict passed between nodes.

Design (Plan 29 §Phase 2):

- Per-node ``outputs`` / ``inputs`` / ``branches`` are each **bucketed by
  node_id** and merged via a shallow-merge reducer. This preserves the DSL's
  "each node writes to its own slot" semantics that selector references
  (``["node_id", "field"]``) depend on.
- ``trigger_input`` and ``workflow_variables`` are written once at graph
  entry and never modified downstream; last-write-wins reducer is fine
  (and is the default when no ``Annotated`` reducer is set).
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_by_node(
    left: dict[str, dict] | None, right: dict[str, dict] | None,
) -> dict[str, dict]:
    """Shallow merge with right-wins semantics, bucketed by node_id.

    Each top-level key is a node_id; the value is that node's output /
    input / branch bucket. Merging preserves buckets from other nodes
    while letting the current node overwrite its own bucket.
    """
    out: dict[str, dict] = dict(left or {})
    for k, v in (right or {}).items():
        out[k] = v
    return out


class WorkflowState(TypedDict, total=False):
    """Global LangGraph state for one workflow execution.

    All top-level keys are optional (total=False) — a node is free to
    write only what it affects, and the reducers take care of merging
    against the previous state.
    """

    # Per-node resolved inputs (what the node actually received after selector
    # resolution). Frozen at node-start time; read by the process drawer.
    inputs: Annotated[dict[str, dict], merge_by_node]

    # Per-node outputs. Downstream selectors read ``state["outputs"][nid][field]``.
    outputs: Annotated[dict[str, dict], merge_by_node]

    # Per-node branch emitted by the node (e.g. question-classifier's
    # ``category_id``). Read by ``add_conditional_edges`` route functions.
    branches: Annotated[dict[str, str | None], merge_by_node]

    # Trigger payload (content / conversation_id / history / metadata for
    # Workflow Agent runs; arbitrary dict for webhook runs).
    trigger_input: dict[str, Any]

    # Workflow-level variables declared in the DSL (``workflow_variables``),
    # flattened into a name → value dict at compile time.
    workflow_variables: dict[str, Any]


def initial_state(
    trigger_input: dict[str, Any] | None,
    workflow_variables: dict[str, Any] | None = None,
) -> WorkflowState:
    """Build the starting state to pass into ``compiled.ainvoke`` / ``astream``.

    All per-node buckets start empty; nodes fill them in as they run.
    """
    return {
        "inputs": {},
        "outputs": {},
        "branches": {},
        "trigger_input": dict(trigger_input or {}),
        "workflow_variables": dict(workflow_variables or {}),
    }
