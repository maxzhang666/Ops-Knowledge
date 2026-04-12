"""Standalone tests for context builder (no DB required)."""
from app.chat.context import build_context


def test_build_context_empty():
    result = build_context([], None)
    assert result == ""


def test_build_context_messages_only():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = build_context(messages)
    assert "user: Hello" in result
    assert "assistant: Hi there" in result


def test_build_context_with_summary():
    messages = [{"role": "user", "content": "question"}]
    result = build_context(messages, memory_summary="Previous discussion about X")
    assert "[Conversation Summary]" in result
    assert "Previous discussion about X" in result
    assert "user: question" in result


def test_build_context_trims_to_max_recent():
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
    result = build_context(messages, max_recent=5)
    assert "msg 15" in result
    assert "msg 19" in result
    assert "msg 14" not in result


def test_build_context_max_recent_larger_than_messages():
    messages = [{"role": "user", "content": "only one"}]
    result = build_context(messages, max_recent=10)
    assert "user: only one" in result
