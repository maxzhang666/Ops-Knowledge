"""Normalized event stream that every HandlerAdapter yields.

Different handler types (Simple Agent SSE tuples, Workflow node events,
MCP CallToolResult) all get translated into this single shape so the
SSE layer renders identically regardless of route.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrchestratorEvent:
    """Single event in the dispatch stream.

    ``type`` discriminator:
    - ``handler_invoked``: emitted once when dispatch begins; data carries
      which handler + id + latency_start_ms
    - ``thinking``: forwarded from downstream reasoning
    - ``retrieval_info``: forwarded from RAG pipeline
    - ``content_delta``: main content stream
    - ``orchestrator_decision``: debug-only, routing decision summary
    - ``message_end``: emitted once by Orchestrator (not the adapter)
    - ``error``: unrecoverable handler error; content string renderable to user
    """
    type: str
    data: dict[str, Any] = field(default_factory=dict)
