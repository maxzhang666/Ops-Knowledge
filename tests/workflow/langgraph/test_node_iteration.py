"""LangGraph-direct iteration node tests.

Drives the outer workflow via ``compile_dsl + ainvoke``; IterationNode
compiles ``blocks + block_edges`` per outer execution as a subgraph with
``allow_non_trigger_entry=True`` and invokes it per item.

Covered:
  1. Sequential iteration: items → prefixed echo outputs
  2. Parallel iteration (order preserved by gather).
  3. ``output_selector`` field harvesting (with / without field).
  4. Subgraph entry via in-degree-0 (dropping inner start) still works.
"""
from __future__ import annotations

import pytest

from app.workflow.dsl import parse_dsl
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.state import initial_state
from app.workflow.nodes.registry import load_builtin_nodes


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _load_nodes() -> None:
    load_builtin_nodes()


def _outer_dsl(parallel: bool = False, *, include_inner_start: bool = True):
    """Outer: start → iteration(items=$.trigger.items, sub=echo)."""
    blocks: list[dict] = []
    block_edges: list[dict] = []
    if include_inner_start:
        blocks.append({"id": "inner_s", "type": "start", "data": {}})
        block_edges.append({"source": "inner_s", "target": "inner"})
    blocks.append({
        "id": "inner",
        "type": "builtin.echo",
        "data": {
            "prefix": "i-",
            "inputs": {"text": ["vars", "trigger", "item"]},
        },
    })

    return parse_dsl({
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "s", "type": "start", "data": {}},
                {
                    "id": "it",
                    "type": "iteration",
                    "data": {
                        "inputs": {"items": ["vars", "trigger", "items"]},
                        "output_selector": ["inner", "text"],
                        "parallel": parallel,
                        "max_parallel": 3,
                    },
                    "blocks": blocks,
                    "block_edges": block_edges,
                },
            ],
            "edges": [{"source": "s", "target": "it"}],
        },
        "workflow_variables": [],
    })


async def test_iteration_sequential_via_langgraph() -> None:
    compiled = compile_dsl(_outer_dsl(parallel=False))
    result = await compiled.ainvoke(
        initial_state({"items": ["a", "b", "c"]}),
    )
    assert result["outputs"]["it"]["results"] == ["i-a", "i-b", "i-c"]


async def test_iteration_parallel_preserves_order() -> None:
    compiled = compile_dsl(_outer_dsl(parallel=True))
    result = await compiled.ainvoke(
        initial_state({"items": [1, 2, 3, 4]}),
    )
    # asyncio.gather preserves input order regardless of completion order.
    assert result["outputs"]["it"]["results"] == ["i-1", "i-2", "i-3", "i-4"]


async def test_iteration_subgraph_without_inner_start() -> None:
    """Subgraph entry falls back to in-degree-0 node when no start exists —
    required because the outer trigger is the only manifest-level trigger."""
    compiled = compile_dsl(_outer_dsl(include_inner_start=False))
    result = await compiled.ainvoke(
        initial_state({"items": ["x"]}),
    )
    assert result["outputs"]["it"]["results"] == ["i-x"]


async def test_iteration_output_selector_full_bucket() -> None:
    """When ``output_selector`` has only node_id (no field), the whole bucket
    is returned per item."""
    raw = {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "s", "type": "start", "data": {}},
                {
                    "id": "it",
                    "type": "iteration",
                    "data": {
                        "inputs": {"items": ["vars", "trigger", "items"]},
                        "output_selector": ["inner"],  # no field
                        "parallel": False,
                    },
                    "blocks": [
                        {"id": "inner_s", "type": "start", "data": {}},
                        {
                            "id": "inner",
                            "type": "builtin.echo",
                            "data": {
                                "prefix": ">",
                                "inputs": {"text": ["vars", "trigger", "item"]},
                            },
                        },
                    ],
                    "block_edges": [{"source": "inner_s", "target": "inner"}],
                },
            ],
            "edges": [{"source": "s", "target": "it"}],
        },
        "workflow_variables": [],
    }
    compiled = compile_dsl(parse_dsl(raw))
    result = await compiled.ainvoke(initial_state({"items": ["a"]}))
    first = result["outputs"]["it"]["results"][0]
    assert isinstance(first, dict)
    assert first.get("text") == ">a"
