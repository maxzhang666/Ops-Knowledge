"""Phase 1 health check — verifies the LangGraph dependency installs and
the core API is importable. No real workflow execution yet; that lands in
Phase 2.
"""
from __future__ import annotations

import os

import pytest


def test_langchain_tracing_is_disabled() -> None:
    """Config must set ``LANGCHAIN_TRACING_V2=false`` at import time so the
    transitive LangChain tracer never POSTs to LangSmith."""
    from app.core import config  # noqa: F401 — side effect: env var set

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"


def test_langgraph_imports() -> None:
    """The ``langgraph`` package and ``StateGraph`` symbol must be importable
    once ``pip install -r requirements.txt`` has been run."""
    pytest.importorskip("langgraph")
    from langgraph.graph import StateGraph  # noqa: F401


def test_state_module_imports() -> None:
    """Our state module must load cleanly under Phase 1 skeleton."""
    from app.workflow.langgraph.state import WorkflowState, merge_by_node

    # Reducer basic sanity — later phases add thorough tests.
    assert merge_by_node({"a": {"x": 1}}, {"b": {"y": 2}}) == {"a": {"x": 1}, "b": {"y": 2}}
    assert merge_by_node({"a": {"x": 1}}, {"a": {"x": 2}}) == {"a": {"x": 2}}
    assert merge_by_node(None, {"a": {}}) == {"a": {}}
    assert merge_by_node({"a": {}}, None) == {"a": {}}
    # TypedDict doesn't enforce at runtime, but the class must be importable.
    assert WorkflowState.__name__ == "WorkflowState"


def test_compiler_is_callable() -> None:
    """Phase 2 implemented compile_dsl — now import-callable (full coverage
    in ``test_compile_simple.py`` etc.)."""
    from app.workflow.langgraph.compiler import compile_dsl

    assert callable(compile_dsl)
