"""Built-in LangChain tools for Agent runtime (Plan 30 M2).

Closure-factory pattern: ``build_builtin_tools(ctx)`` returns a fresh
list of ``@tool`` callables with per-invocation context (db_factory,
user_id, kb_ids) captured in closure. Keeps tool signatures clean
(model sees only semantic args) while giving tools the handles they
need to actually do work.

Why closures over ``ContextVar``: lifetime is explicit, no cross-request
leakage risk, easy to stub in unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.tools import BaseTool

from app.agent.tools.code_execute import make_code_execute
from app.agent.tools.http_request import make_http_request
from app.agent.tools.knowledge_search import make_knowledge_search


@dataclass
class ToolContext:
    """Per-invocation handles captured by the tool factories.

    ``db_factory`` is a zero-arg callable returning an *async context
    manager* yielding ``AsyncSession`` — e.g. ``async_session`` from
    ``app.core.database``. We take a factory rather than a live session
    so each tool call gets its own short-lived session, avoiding lock
    contention in long-running ReAct loops.
    """
    db_factory: Callable[[], Any]
    user_id: str | None = None
    agent_id: str | None = None
    kb_ids: list[str] = field(default_factory=list)
    folder_ids: list[str] = field(default_factory=list)


TOOL_BUILDERS: dict[str, Callable[[ToolContext], BaseTool]] = {
    "knowledge_search": make_knowledge_search,
    "code_execute": make_code_execute,
    "http_request": make_http_request,
}


def build_builtin_tools(
    ctx: ToolContext, enabled: list[str] | None = None,
) -> list[BaseTool]:
    """Build the requested subset. ``enabled=None`` → all known tools.

    Unknown names are skipped silently (forward-compat when new tool
    names land in ``config.builtin_tools`` before the backend does).
    """
    names = enabled if enabled is not None else list(TOOL_BUILDERS.keys())
    out: list[BaseTool] = []
    for name in names:
        builder = TOOL_BUILDERS.get(name)
        if builder is None:
            continue
        out.append(builder(ctx))
    return out


__all__ = ["ToolContext", "build_builtin_tools", "TOOL_BUILDERS"]
