"""Built-in tool closure factories — verify ctx capture + signatures.

We don't invoke the tool bodies (they hit Redis/Milvus/Runner). Goal is
ensuring the factory pattern is sound: tools are LangChain ``BaseTool``
instances, capture the right ctx fields, and ``build_builtin_tools``
honors ``enabled`` filtering.
"""
from contextlib import asynccontextmanager

import pytest
from langchain_core.tools import BaseTool

from app.agent.tools import TOOL_BUILDERS, ToolContext, build_builtin_tools


@asynccontextmanager
async def _fake_db_factory():
    yield object()


def _ctx(**overrides) -> ToolContext:
    base = dict(
        db_factory=_fake_db_factory,
        user_id="u1",
        agent_id="a1",
        kb_ids=["kb1"],
        folder_ids=[],
    )
    base.update(overrides)
    return ToolContext(**base)


def test_build_all_by_default():
    tools = build_builtin_tools(_ctx())
    names = [t.name for t in tools]
    assert set(names) == {"knowledge_search", "code_execute", "http_request"}
    for t in tools:
        assert isinstance(t, BaseTool)


def test_build_subset():
    tools = build_builtin_tools(_ctx(), enabled=["knowledge_search"])
    assert [t.name for t in tools] == ["knowledge_search"]


def test_build_unknown_skipped():
    tools = build_builtin_tools(_ctx(), enabled=["knowledge_search", "not_a_tool"])
    assert [t.name for t in tools] == ["knowledge_search"]


def test_builders_registry_complete():
    # If someone adds a tool file but forgets the registry entry, tests here catch it
    assert set(TOOL_BUILDERS.keys()) == {"knowledge_search", "code_execute", "http_request"}


def test_knowledge_search_has_schema():
    tool = build_builtin_tools(_ctx(), enabled=["knowledge_search"])[0]
    # Docstring becomes description; schema validates args
    assert tool.description
    assert "query" in tool.args


def test_code_execute_has_schema():
    tool = build_builtin_tools(_ctx(), enabled=["code_execute"])[0]
    assert "code" in tool.args


def test_http_request_has_schema():
    tool = build_builtin_tools(_ctx(), enabled=["http_request"])[0]
    assert "method" in tool.args
    assert "url" in tool.args


@pytest.mark.asyncio
async def test_knowledge_search_empty_kbs_returns_helpful_msg():
    """With no kb_ids bound the tool should short-circuit with a clear
    message rather than raising — the agent needs a usable string."""
    tool = build_builtin_tools(_ctx(kb_ids=[]), enabled=["knowledge_search"])[0]
    result = await tool.ainvoke({"query": "anything"})
    assert "No knowledge base" in result
