"""Standalone tests for prompt assembly (no DB required).

Covers the Dify-style variable substitution engine in app/chat/prompt.py:
- FALLBACK_SYSTEM_PROMPT used when agent.system_prompt is None/empty
- render_variables replaces {{var}} occurrences, missing vars → empty string
- detect_required_vars enumerates template variables
- format_context_chunks renders retrieval chunks with token budget / empty
  placeholder
- assemble_prompt builds the messages[] with system + trimmed history + user
"""
from app.chat.prompt import (
    EMPTY_CONTEXT_PLACEHOLDER,
    FALLBACK_SYSTEM_PROMPT,
    assemble_prompt,
    detect_required_vars,
    format_context_chunks,
    render_variables,
)


# ── FALLBACK_SYSTEM_PROMPT ────────────────────────────────────────────────

def test_assemble_prompt_uses_fallback_when_system_empty():
    messages = assemble_prompt(
        system_prompt=None, variables={}, history=[], query="What is X?",
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == FALLBACK_SYSTEM_PROMPT
    assert messages[-1] == {"role": "user", "content": "What is X?"}


def test_assemble_prompt_uses_custom_system():
    messages = assemble_prompt(
        system_prompt="Custom system", variables={}, history=[], query="q",
    )
    assert messages[0]["content"] == "Custom system"


# ── render_variables ──────────────────────────────────────────────────────

def test_render_variables_substitutes_known_keys():
    assert render_variables("Hi {{name}}!", {"name": "Ada"}) == "Hi Ada!"


def test_render_variables_missing_keys_become_empty():
    assert render_variables("a {{x}} b {{y}} c", {"x": "1"}) == "a 1 b  c"


def test_render_variables_handles_empty_template():
    assert render_variables("", {"x": "1"}) == ""
    assert render_variables(None, {"x": "1"}) == ""


def test_render_variables_tolerates_whitespace_inside_braces():
    assert render_variables("{{ name }}", {"name": "X"}) == "X"


# ── detect_required_vars ──────────────────────────────────────────────────

def test_detect_required_vars_collects_all_placeholders():
    tpl = "answer using {{context}} and {{history_summary}} for {{query}}"
    assert detect_required_vars(tpl) == {"context", "history_summary", "query"}


def test_detect_required_vars_empty_template_returns_empty_set():
    assert detect_required_vars("") == set()
    assert detect_required_vars(None) == set()


# ── format_context_chunks ─────────────────────────────────────────────────

def test_format_context_chunks_empty_returns_placeholder():
    assert format_context_chunks([], max_tokens=1000) == EMPTY_CONTEXT_PLACEHOLDER


def test_format_context_chunks_numbers_entries():
    chunks = [
        {"content": "Chunk one content", "title": "Doc A"},
        {"content": "Chunk two content", "title": "Doc B"},
    ]
    rendered = format_context_chunks(chunks, max_tokens=1000)
    assert "[1] Doc A" in rendered
    assert "[2] Doc B" in rendered
    assert "Chunk one content" in rendered


def test_format_context_chunks_respects_token_budget():
    """With a tiny budget, only chunks that fit are emitted."""
    big = "x" * 400  # ~100 tokens by the crude 4-chars-per-token heuristic
    chunks = [{"content": big, "title": "T1"}, {"content": big, "title": "T2"}]
    rendered = format_context_chunks(chunks, max_tokens=50)
    # Budget too small for even the first chunk → falls through to placeholder.
    assert rendered == EMPTY_CONTEXT_PLACEHOLDER


def test_format_context_chunks_omits_title_when_absent():
    chunks = [{"content": "bare"}]
    rendered = format_context_chunks(chunks, max_tokens=1000)
    assert rendered.startswith("[1] bare")


# ── assemble_prompt history trimming ──────────────────────────────────────

def test_assemble_prompt_preserves_history_order():
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
    ]
    messages = assemble_prompt(
        system_prompt=None, variables={}, history=history, query="q",
    )
    # system + 3 history + user query
    assert len(messages) == 5
    assert messages[1:4] == history
    assert messages[-1] == {"role": "user", "content": "q"}


def test_assemble_prompt_trims_oldest_history_over_budget():
    """Oldest items drop first when the history budget is exceeded."""
    long = "y" * 400  # ~100 tokens each
    history = [
        {"role": "user", "content": long},
        {"role": "user", "content": long},
        {"role": "user", "content": "recent"},
    ]
    # 200 tokens * 30% = 60 tokens budget → only "recent" (tiny) fits.
    messages = assemble_prompt(
        system_prompt=None, variables={}, history=history,
        query="q", max_context_tokens=200,
    )
    assert messages[1] == {"role": "user", "content": "recent"}
    assert messages[-1]["content"] == "q"


def test_assemble_prompt_substitutes_variables_in_system():
    messages = assemble_prompt(
        system_prompt="Answer {{query}} using {{context}}",
        variables={"query": "Q?", "context": "CTX"},
        history=[],
        query="real-query",
    )
    assert messages[0]["content"] == "Answer Q? using CTX"
    assert messages[-1]["content"] == "real-query"
