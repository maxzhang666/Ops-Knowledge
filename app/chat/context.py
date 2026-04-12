from __future__ import annotations


def build_context(
    messages: list[dict],
    memory_summary: str | None = None,
    max_recent: int = 10,
) -> str:
    """Build conversation context string from messages and optional memory summary.

    Returns a formatted string combining the memory summary (if any)
    with the most recent messages.
    """
    parts: list[str] = []

    if memory_summary:
        parts.append(f"[Conversation Summary]\n{memory_summary}")

    recent = messages[-max_recent:] if len(messages) > max_recent else messages
    for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")

    return "\n\n".join(parts)
