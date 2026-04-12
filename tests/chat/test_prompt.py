"""Standalone tests for prompt assembly (no DB required)."""
from app.chat.prompt import DEFAULT_SYSTEM_PROMPT, assemble_prompt


def test_assemble_prompt_minimal():
    result = assemble_prompt(None, [], [], "What is X?")
    assert result[0]["role"] == "system"
    assert result[0]["content"] == DEFAULT_SYSTEM_PROMPT
    assert result[-1]["role"] == "user"
    assert result[-1]["content"] == "What is X?"


def test_assemble_prompt_with_custom_system():
    result = assemble_prompt("Custom system", [], [], "query")
    assert result[0]["content"] == "Custom system"


def test_assemble_prompt_with_chunks():
    chunks = [
        {"content": "Chunk one content", "title": "Doc A"},
        {"content": "Chunk two content", "title": "Doc B"},
    ]
    result = assemble_prompt(None, chunks, [], "query")
    # system + context + query = 3 messages
    assert len(result) == 3
    context_msg = result[1]
    assert context_msg["role"] == "system"
    assert "[1] Doc A" in context_msg["content"]
    assert "[2] Doc B" in context_msg["content"]


def test_assemble_prompt_with_history():
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    result = assemble_prompt(None, [], history, "follow-up")
    # system + 2 history + query = 4
    assert len(result) == 4
    assert result[1]["role"] == "user"
    assert result[2]["role"] == "assistant"
    assert result[3]["content"] == "follow-up"


def test_assemble_prompt_trims_history_by_budget():
    # Create a very large history that exceeds 30% budget
    history = [
        {"role": "user", "content": "x" * 10000},
        {"role": "assistant", "content": "y" * 10000},
        {"role": "user", "content": "recent question"},
    ]
    result = assemble_prompt(None, [], history, "query", max_context_tokens=100)
    # With budget of 100 tokens * 0.3 = 30 tokens (~120 chars), only last message fits
    user_messages = [m for m in result if m["role"] == "user"]
    assert user_messages[-1]["content"] == "query"


def test_assemble_prompt_trims_chunks_by_budget():
    chunks = [
        {"content": "a" * 2000, "title": "Big"},
        {"content": "small content", "title": "Small"},
    ]
    result = assemble_prompt(None, chunks, [], "query", max_context_tokens=200)
    # With budget 200*0.6=120 tokens (~480 chars), big chunk fits but may truncate second
    context_msgs = [m for m in result if m["role"] == "system" and "Reference" in m.get("content", "")]
    assert len(context_msgs) <= 1
