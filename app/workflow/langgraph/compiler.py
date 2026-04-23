"""Compile a parsed Workflow DSL into a LangGraph ``StateGraph``.

Phase 2 scope (current): entry point + plain edges + conditional routing
via ``sourceHandle``. No subgraphs (iteration stays unsupported until
Phase 3), no checkpointer (added Phase 4).

See Plan 29 §Phase 2 §Compiler and Spec 02 §Per-node mapping overview.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from langgraph.graph import END, StateGraph

from app.workflow.dsl import EdgeDef, NodeDef, WorkflowDSL
from app.workflow.nodes.registry import registry

from .node_adapters import build_node_adapter
from .state import WorkflowState


__all__ = ["compile_dsl"]


def compile_dsl(
    dsl: WorkflowDSL,
    checkpointer=None,
    *,
    allow_non_trigger_entry: bool = False,
):
    """DSL → compiled LangGraph. Caller invokes via ``ainvoke`` / ``astream``.

    Only nodes reachable from an entry are registered (same rule as the
    legacy scheduler — orphan draft nodes don't execute).

    ``checkpointer``: optional ``BaseCheckpointSaver``. When provided and
    invocations pass ``config={"configurable": {"thread_id": ...}}``, state
    is persisted after each node and can be resumed (long-flow crash
    recovery, multi-turn conversation accumulation, HITL pause/resume).

    ``allow_non_trigger_entry``: when True, the entry point is the unique
    in-degree-0 node (no trigger manifest required). Used by compound
    subgraphs (iteration block_edges) whose author's DSL slice contains
    regular nodes only, not a trigger.
    """
    nodes_by_id = {n.id: n for n in dsl.graph.nodes}
    entry_ids = _entry_nodes(
        dsl.graph.nodes, dsl.graph.edges,
        allow_non_trigger_entry=allow_non_trigger_entry,
    )
    reachable = _reachable_from(entry_ids, dsl.graph.edges)
    if not reachable:
        raise ValueError(
            "Workflow has no trigger node — nothing to execute. "
            "Add a 'start' node and connect downstream nodes to it."
        )

    graph = StateGraph(WorkflowState)

    # Register one LangGraph node per reachable DSL node.
    for nid in reachable:
        node_def = nodes_by_id[nid]
        graph.add_node(nid, build_node_adapter(node_def))

    # Group edges by source to decide normal vs conditional.
    out_edges: dict[str, list[EdgeDef]] = defaultdict(list)
    for e in dsl.graph.edges:
        if e.source in reachable and e.target in reachable:
            out_edges[e.source].append(e)

    for source_id, edges in out_edges.items():
        if all(e.sourceHandle is None for e in edges):
            # Plain fan-out: every edge's target runs once the source finishes.
            for e in edges:
                graph.add_edge(source_id, e.target)
        else:
            # Conditional routing: sourceHandle matches the node's emitted branch.
            route_fn = _make_route_fn(source_id, edges)
            path_map = {
                (e.sourceHandle or "_default"): e.target
                for e in edges
            }
            # Unmatched branches fall through to END (mirrors legacy scheduler's
            # "all inbound edges inactive → skip" semantics for terminal cases).
            path_map.setdefault("_end", END)
            graph.add_conditional_edges(source_id, route_fn, path_map)

    # Terminal (no-outgoing) nodes get an edge to END so LangGraph knows the
    # graph is finished when they complete.
    for nid in reachable:
        if not out_edges.get(nid):
            graph.add_edge(nid, END)

    # Entry point: the single entry determined above (trigger for regular
    # workflows, in-degree-0 node for subgraphs).
    if len(entry_ids) != 1:
        raise ValueError(
            f"Workflow must have exactly one entry node, found {len(entry_ids)}"
        )
    graph.set_entry_point(entry_ids[0])

    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


def _is_trigger(node: NodeDef) -> bool:
    try:
        cls = registry.get(node.type, node.type_version)
    except KeyError:
        return node.type == "start"
    manifest = getattr(cls, "manifest", None)
    return bool(manifest and manifest.category == "trigger")


def _entry_nodes(
    nodes: list[NodeDef], edges: list[EdgeDef],
    *, allow_non_trigger_entry: bool,
) -> list[str]:
    """Resolve the entry node list. Regular workflows use trigger manifest;
    subgraphs fall back to the in-degree-0 node (expected to be unique)."""
    if not allow_non_trigger_entry:
        return [n.id for n in nodes if _is_trigger(n)]
    indeg: dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        if e.target in indeg:
            indeg[e.target] += 1
    return [nid for nid, d in indeg.items() if d == 0]


def _reachable_from(
    starts: list[str], edges: list[EdgeDef],
) -> set[str]:
    """BFS from given entry ids → set of reachable node ids."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.source].append(e.target)
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        for t in adj.get(nid, []):
            stack.append(t)
    return seen


def _make_route_fn(source_id: str, edges: list[EdgeDef]) -> Callable:
    """Return a route function that maps the node's emitted branch to a
    downstream edge's ``sourceHandle``. Edges without ``sourceHandle``
    are treated as the default ("always active") path.
    """
    handles = {e.sourceHandle for e in edges if e.sourceHandle is not None}

    def route(state: WorkflowState) -> str:
        branch = (state.get("branches") or {}).get(source_id)
        if branch is not None and branch in handles:
            return branch
        # Default edge present? Route there when no handle matches.
        if any(e.sourceHandle is None for e in edges):
            return "_default"
        # Nothing matches — terminate this branch.
        return "_end"

    return route
