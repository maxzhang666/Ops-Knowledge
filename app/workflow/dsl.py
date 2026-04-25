"""Workflow DSL: Pydantic schema + structural validator.

The DSL is the user-facing contract. It's stored as JSONB on `workflows.graph_data`
(editable draft) and `workflows.published_graph_data` (frozen runtime copy).

Strict validation: unknown fields at the root / edge level are rejected. Node
`data` blocks intentionally allow extras because node-specific configs are
polymorphic and get validated by each node's own `validate()` at run-time.

See spec `02-workflow-engine.md` §Workflow DSL for the full design rationale.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DSL_VERSION = "1.0"


class DSLValidationError(ValueError):
    """Raised for structural / semantic DSL problems beyond Pydantic shape."""


class ErrorHandling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["abort", "retry", "default-value", "fail-branch"] = "abort"
    max_retries: int = Field(0, ge=0, le=10)
    retry_interval: float = Field(1.0, ge=0, le=60)
    default_value: Any | None = None


class EdgeDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    source: str
    target: str
    # Branch identifier for conditional nodes (e.g. "true" / "false" / category id).
    sourceHandle: str | None = None


class NodeDef(BaseModel):
    # Node `data` holds polymorphic per-type config — allow extras there, but
    # the NodeDef wrapper itself is strict.
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    type_version: str = "1.0"
    position: dict[str, float] | None = None  # {"x": ..., "y": ...}, scheduler ignores
    data: dict[str, Any] = Field(default_factory=dict)
    error_handling: ErrorHandling = Field(default_factory=ErrorHandling)
    # Compound nodes (iteration / loop) carry a sub-graph.
    blocks: list["NodeDef"] | None = None
    block_edges: list[EdgeDef] | None = None


class GraphDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[NodeDef]
    edges: list[EdgeDef]


class WorkflowVariableDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    type: Literal["string", "number", "boolean", "object", "array"]
    default: Any | None = None


class WorkflowDSL(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dsl_version: str = DSL_VERSION
    graph: GraphDef
    workflow_variables: list[WorkflowVariableDef] = Field(default_factory=list)
    # Plan 27 M2 — 触发配置（按 trigger_type 解读）。
    #   governance_event: {"kinds": [...], "kb_ids": [...], "severities": [...]}
    trigger_config: dict[str, Any] = Field(default_factory=dict)


NodeDef.model_rebuild()


def _assert_acyclic(graph: GraphDef) -> None:
    """Kahn's algorithm. Raises DSLValidationError on cycle."""
    in_degree = {n.id: 0 for n in graph.nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        if e.target in in_degree:
            in_degree[e.target] += 1
        if e.source in adj:
            adj[e.source].append(e.target)

    queue = [nid for nid, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        nid = queue.pop(0)
        visited += 1
        for t in adj[nid]:
            in_degree[t] -= 1
            if in_degree[t] == 0:
                queue.append(t)
    if visited != len(graph.nodes):
        raise DSLValidationError("Graph contains a cycle")


def validate_structure(dsl: WorkflowDSL) -> None:
    """Semantic checks beyond shape: uniqueness, edge references, Start node,
    acyclicity (main + compound sub-graphs).
    """
    node_ids = [n.id for n in dsl.graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise DSLValidationError("Duplicate node IDs in graph")
    id_set = set(node_ids)

    for e in dsl.graph.edges:
        if e.source not in id_set:
            raise DSLValidationError(f"Edge source '{e.source}' not found")
        if e.target not in id_set:
            raise DSLValidationError(f"Edge target '{e.target}' not found")

    start_nodes = [n for n in dsl.graph.nodes if n.type == "start"]
    if len(start_nodes) == 0:
        raise DSLValidationError("Graph must contain exactly one 'start' node")
    if len(start_nodes) > 1:
        raise DSLValidationError("Multiple 'start' nodes not allowed")

    _assert_acyclic(dsl.graph)

    for n in dsl.graph.nodes:
        if n.blocks is not None:
            sub = GraphDef(nodes=n.blocks, edges=n.block_edges or [])
            # Validate edge references BEFORE cycle detection so the error
            # message is accurate for compound-node authoring mistakes.
            sub_ids = {bn.id for bn in sub.nodes}
            for be in sub.edges:
                if be.source not in sub_ids or be.target not in sub_ids:
                    raise DSLValidationError(
                        f"Compound node '{n.id}' block_edges reference unknown sub-node"
                    )
            _assert_acyclic(sub)


def parse_dsl(raw: dict | None) -> WorkflowDSL:
    """Parse + structural-validate. Raises DSLValidationError on any issue.

    Empty graphs (None or {"graph": {"nodes": [], "edges": []}}) are accepted
    as valid drafts — they just can't be published (service.publish enforces).
    """
    if not raw:
        return WorkflowDSL(graph=GraphDef(nodes=[], edges=[]))
    dsl = WorkflowDSL.model_validate(raw)
    if dsl.graph.nodes:
        validate_structure(dsl)
    return dsl


def parse_dsl_loose(raw: dict | None) -> WorkflowDSL:
    """Shape-only validation — used for `update` (draft save). Authors save
    WIP workflows constantly in incomplete states (no Start yet, floating
    nodes, etc.) and shouldn't be blocked. Full structural enforcement stays
    on `publish`.
    """
    if not raw:
        return WorkflowDSL(graph=GraphDef(nodes=[], edges=[]))
    return WorkflowDSL.model_validate(raw)
