"""Iteration — compound node running a sub-workflow per array item.

Per item we compile ``blocks + block_edges`` into a LangGraph subgraph
(via ``compile_dsl(..., allow_non_trigger_entry=True)``) and invoke it
with ``trigger_input={"item", "index"}``. Results are harvested via the
``output_selector``. Subgraphs run without a checkpointer so iteration
doesn't pollute the outer thread's state.
"""
from __future__ import annotations

import asyncio

from app.workflow.dsl import EdgeDef, GraphDef, NodeDef, WorkflowDSL
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.state import initial_state
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class IterationNode(AbstractNode):
    manifest = NodeManifest(
        type="iteration",
        category="logic",
        name="Iteration",
        description="Run a sub-workflow for each item in an input array.",
        is_compound=True,
    )
    io = NodeIO(
        inputs={"items": {"type": "array"}},
        outputs={"results": {"type": "array"}},
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "output_selector": {
                    "type": "array",
                    "description": "Inside sub-flow: [node_id, field] to harvest per iteration",
                    "items": {"type": "string"},
                },
                "parallel": {"type": "boolean", "default": False},
                "max_parallel": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["output_selector"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if "items" not in ctx.inputs:
            raise ValueError("Iteration: missing 'items' input")
        if not isinstance(ctx.inputs["items"], list):
            raise ValueError("Iteration: 'items' must be a list")
        if not ctx.config.get("output_selector"):
            raise ValueError("Iteration: 'output_selector' required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        items: list = ctx.inputs["items"]
        raw_blocks = ctx.config.get("blocks") or []
        raw_edges = ctx.config.get("block_edges") or []
        if not raw_blocks:
            raise RuntimeError("Iteration: compound node has no sub-graph (blocks)")

        sub_nodes = [NodeDef.model_validate(b) for b in raw_blocks]
        sub_edges = [EdgeDef.model_validate(e) for e in raw_edges]
        sub_dsl = WorkflowDSL(graph=GraphDef(nodes=sub_nodes, edges=sub_edges))

        # Compile once per iteration-node execution, reuse across items. The
        # subgraph has no trigger node (the outer workflow's trigger is the
        # only one in the run); fall back to in-degree-0 entry.
        sub_compiled = compile_dsl(sub_dsl, allow_non_trigger_entry=True)

        selector: list[str] = list(ctx.config["output_selector"])
        parallel = bool(ctx.config.get("parallel", False))
        max_parallel = int(ctx.config.get("max_parallel", 5))

        async def _run_one(idx: int, item):
            # Pass item/index via trigger_input so sub-nodes reference them
            # through the standard $.trigger_input.* path.
            final = await sub_compiled.ainvoke(
                initial_state(trigger_input={"item": item, "index": idx}),
            )
            node_id = selector[0]
            field = selector[1] if len(selector) > 1 else None
            out = (final.get("outputs") or {}).get(node_id, {})
            return out if field is None else (out or {}).get(field)

        if not parallel:
            results = [await _run_one(i, it) for i, it in enumerate(items)]
        else:
            sem = asyncio.Semaphore(max_parallel)

            async def _bound(i, it):
                async with sem:
                    return await _run_one(i, it)

            results = await asyncio.gather(*[_bound(i, it) for i, it in enumerate(items)])

        return NodeResult(outputs={"results": results})
