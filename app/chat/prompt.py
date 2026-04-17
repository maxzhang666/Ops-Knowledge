"""Prompt rendering — variable substitution engine (Dify-style).

The platform does NOT inject any built-in system prompt. The user's
``agent.system_prompt`` IS the system prompt sent to the LLM after
``{{variable}}`` substitution.

Supported variables (see `16-chat-rag-pipeline.md`):
  {{context}}         — numbered retrieval chunks
  {{history_summary}} — conversation memory summary (if any)
  {{query}}           — current user query
  {{knowledge_names}} — comma-separated linked KB names
  {{kb_count}}        — number of linked KBs
"""
from __future__ import annotations

import re

# Fallback prompt for agents with empty system_prompt (should rarely happen
# because new agents are pre-filled with a template at creation time).
FALLBACK_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions accurately and concisely."
)

# Shown inside {{context}} when retrieval returned nothing. Users can detect
# this in their prompt and decide how to behave.
EMPTY_CONTEXT_PLACEHOLDER = "(未找到相关参考资料)"

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed CJK/English."""
    return max(1, len(text) // 4)


def detect_required_vars(template: str) -> set[str]:
    """Return the set of ``{{variable}}`` names used in the template.

    Used to decide whether to run retrieval ({{context}}) and/or fetch memory
    summary ({{history_summary}}) before message assembly.
    """
    return set(_VAR_RE.findall(template or ""))


def render_variables(template: str, variables: dict[str, str]) -> str:
    """Replace every ``{{var}}`` with its value from ``variables``.

    Missing variables render as empty strings — never raises.
    """
    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        return str(variables.get(name, ""))
    return _VAR_RE.sub(_sub, template or "")


def format_context_chunks(
    chunks: list[dict], max_tokens: int,
) -> str:
    """Render retrieval chunks as ``[1] <title>\\n<content>\\n\\n[2] ...``.

    Truncates at ``max_tokens``; if no chunks, returns the empty placeholder.
    """
    if not chunks:
        return EMPTY_CONTEXT_PLACEHOLDER
    parts: list[str] = []
    used = 0
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        title = chunk.get("title", "")
        entry = f"[{i}] {title}\n{content}" if title else f"[{i}] {content}"
        t = _estimate_tokens(entry)
        if used + t > max_tokens:
            break
        parts.append(entry)
        used += t
    return "\n\n".join(parts) if parts else EMPTY_CONTEXT_PLACEHOLDER


def assemble_prompt(
    *,
    system_prompt: str | None,
    variables: dict[str, str],
    history: list[dict],
    query: str,
    max_context_tokens: int = 6000,
) -> list[dict]:
    """Build the ``messages[]`` sent to the LLM.

    The final structure (Dify-style):
      [
        system:     rendered(system_prompt, variables),
        system:     "[Conversation Summary] <history_summary>"   # optional
        ...trimmed history...,
        user:       query,
      ]

    History summary is passed as a separate system message (rather than a
    variable) so it doesn't bloat the user's prompt template with
    conditional sections. Users who want finer control can paste
    ``{{history_summary}}`` into their prompt; it will also render there.
    """
    template = (system_prompt or FALLBACK_SYSTEM_PROMPT).strip()
    rendered = render_variables(template, variables)

    messages: list[dict] = [{"role": "system", "content": rendered}]

    # Trim history to budget (30% of context)
    history_budget = int(max_context_tokens * 0.3)
    history_tokens = 0
    trimmed: list[dict] = []
    for msg in reversed(history):
        t = _estimate_tokens(msg.get("content", ""))
        if history_tokens + t > history_budget:
            break
        trimmed.insert(0, msg)
        history_tokens += t
    messages.extend(trimmed)

    messages.append({"role": "user", "content": query})
    return messages
