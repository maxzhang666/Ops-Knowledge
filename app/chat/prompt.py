from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful knowledge assistant. Answer questions based on the provided context. "
    "When using information from the context, cite sources using [N] notation where N is the "
    "chunk number (starting from 1). If the context does not contain relevant information, "
    "clearly state that. Be concise and accurate."
)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed CJK/English."""
    return max(1, len(text) // 4)


def assemble_prompt(
    system_prompt: str | None,
    chunks: list[dict],
    history: list[dict],
    query: str,
    max_context_tokens: int = 6000,
    max_output_tokens: int = 2000,
) -> list[dict]:
    """Assemble the final prompt messages for the LLM.

    Token budget allocation:
      - system: fixed (always included)
      - context chunks: up to 60% of max_context_tokens
      - history: up to 30% of max_context_tokens
      - query: always included (remaining)

    Returns list[dict] in OpenAI message format.
    """
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    messages: list[dict] = [{"role": "system", "content": system}]

    # Build context from chunks (60% budget)
    context_budget = int(max_context_tokens * 0.6)
    context_parts: list[str] = []
    used_tokens = 0
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        title = chunk.get("title", "")
        entry = f"[{i}] {title}\n{content}" if title else f"[{i}] {content}"
        entry_tokens = _estimate_tokens(entry)
        if used_tokens + entry_tokens > context_budget:
            break
        context_parts.append(entry)
        used_tokens += entry_tokens

    if context_parts:
        context_text = "Reference materials:\n\n" + "\n\n".join(context_parts)
        messages.append({"role": "system", "content": context_text})

    # Add history (30% budget)
    history_budget = int(max_context_tokens * 0.3)
    history_tokens = 0
    trimmed_history: list[dict] = []
    for msg in reversed(history):
        msg_tokens = _estimate_tokens(msg.get("content", ""))
        if history_tokens + msg_tokens > history_budget:
            break
        trimmed_history.insert(0, msg)
        history_tokens += msg_tokens

    messages.extend(trimmed_history)

    # Add user query
    messages.append({"role": "user", "content": query})

    return messages
