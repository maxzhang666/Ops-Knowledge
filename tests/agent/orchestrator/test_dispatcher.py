"""Dispatcher + SSE translate + handler adapter signature."""
from types import SimpleNamespace

import pytest

from app.agent.orchestrator.adapters.base import DispatchContext, resolve_template
from app.agent.orchestrator.adapters.sse_translate import translate


def test_sse_translate_pass_through():
    ev = translate("content_delta", {"delta": "hi"})
    assert ev is not None and ev.type == "content_delta"
    assert ev.data == {"delta": "hi"}


def test_sse_translate_swallows_lifecycle():
    assert translate("message_start", {}) is None
    assert translate("message_end", {}) is None


def test_sse_translate_unknown_wraps_as_adapter_extra():
    ev = translate("custom_upstream", {"x": 1})
    assert ev is not None
    assert ev.type == "adapter_extra"
    assert ev.data["upstream_event"] == "custom_upstream"


def test_resolve_template_message():
    ctx = DispatchContext(
        agent_id=SimpleNamespace(),
        conversation_id=None, user_id=None,
        trace_id="t", db_factory=None,
        metadata={"trusted": {"user": {"id": "uid-1"}}, "input": {"ticket": "T-9"}},
    )
    assert resolve_template("$message", ctx, "hello") == "hello"
    assert resolve_template("$user.id", ctx, "x") == "uid-1"
    assert resolve_template("$metadata.input.ticket", ctx, "x") == "T-9"


def test_resolve_template_dict_recurse():
    ctx = DispatchContext(
        agent_id=SimpleNamespace(),
        conversation_id=None, user_id=None,
        trace_id="t", db_factory=None,
        metadata={"trusted": {}, "input": {}},
    )
    got = resolve_template({"a": "$message", "b": "literal", "c": 42}, ctx, "hi")
    assert got == {"a": "hi", "b": "literal", "c": 42}


def test_resolve_template_missing_path_returns_none():
    ctx = DispatchContext(
        agent_id=SimpleNamespace(),
        conversation_id=None, user_id=None,
        trace_id="t", db_factory=None,
        metadata={"trusted": {}, "input": {}},
    )
    assert resolve_template("$metadata.input.nonexistent", ctx, "x") is None
