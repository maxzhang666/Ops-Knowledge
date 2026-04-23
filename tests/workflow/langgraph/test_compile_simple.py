"""Phase 2 Day 4 — smoke tests for the DSL → LangGraph compiler.

Two scenarios covered here:
 1. ``start → answer`` with a literal ``answer`` input — no LLM involved,
    the whole pipeline is in-process. Verifies the compiler produces a
    runnable graph and our state model propagates outputs correctly.
 2. Orphan nodes (not connected to the trigger) are silently excluded
    from the compiled graph, matching legacy scheduler behaviour.

Streaming, conditional routing, and LLM nodes arrive in Day 5+.
"""
from __future__ import annotations

import pytest

from app.workflow.dsl import parse_dsl
from app.workflow.langgraph.compiler import compile_dsl
from app.workflow.langgraph.state import initial_state


pytestmark = pytest.mark.asyncio


async def test_compile_start_answer_literal() -> None:
    """start → answer, answer input is a literal string — minimal run."""
    raw = {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "position": {"x": 0, "y": 0},
                    "data": {},
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "position": {"x": 200, "y": 0},
                    "data": {"inputs": {"answer": "hello world"}},
                },
            ],
            "edges": [{"source": "start", "target": "answer"}],
        },
        "workflow_variables": [],
    }
    dsl = parse_dsl(raw)
    compiled = compile_dsl(dsl)

    result = await compiled.ainvoke(initial_state({"content": "hi"}))

    # Answer produces outputs["answer"] under its own bucket.
    assert result["outputs"]["answer"]["answer"] == "hello world"
    # Start records whatever it produces; with no declared variables it
    # passes the trigger through.
    assert "start" in result["outputs"]
    # No node emitted a branch.
    assert result["branches"] == {"start": None, "answer": None}


async def test_compile_orphan_nodes_excluded() -> None:
    """A node not connected to the trigger must not be compiled in."""
    raw = {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "answer", "type": "answer",
                 "data": {"inputs": {"answer": "reachable"}}},
                # Orphan: not connected to start, should be skipped entirely.
                {"id": "orphan", "type": "answer",
                 "data": {"inputs": {"answer": "never runs"}}},
            ],
            "edges": [{"source": "start", "target": "answer"}],
        },
        "workflow_variables": [],
    }
    dsl = parse_dsl(raw)
    compiled = compile_dsl(dsl)
    result = await compiled.ainvoke(initial_state({"content": "hi"}))

    assert "answer" in result["outputs"]
    assert "orphan" not in result.get("outputs", {})


async def test_compile_refuses_without_trigger() -> None:
    """Graph with no trigger node must fail loudly, not silently do nothing."""
    raw = {
        "dsl_version": "1.0",
        "graph": {
            "nodes": [
                {"id": "a", "type": "answer",
                 "data": {"inputs": {"answer": "x"}}},
            ],
            "edges": [],
        },
        "workflow_variables": [],
    }
    # parse_dsl's validate_structure already refuses — compiler is a backstop.
    from app.workflow.dsl import DSLValidationError
    with pytest.raises(DSLValidationError):
        parse_dsl(raw)
