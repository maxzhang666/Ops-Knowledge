"""Stream helpers — relay node chunks into LangGraph's custom-stream channel.

Our LLM / Answer nodes keep producing chunks via ``AbstractNode.on_stream``
(see ``app/workflow/nodes/base.py``). At runtime we relay each chunk into
LangGraph's custom stream via ``StreamWriter``; the event bridge then
translates those custom-stream events into our ``stream_chunk`` EventBus
entries, preserving the WebSocket protocol the frontend already consumes.

Payload contract (what we push through ``write_chunk``):

    {
        "kind": "stream_chunk",
        "node_id": <str>,      # which node produced it
        "delta": <str>,         # the chunk text
        "meta": <dict | None>,  # optional per-chunk metadata
    }

The event bridge (``events.py``) reads this shape verbatim; any change
must update both sides.
"""
from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer


def write_chunk(node_id: str, delta: str, meta: dict[str, Any] | None = None) -> None:
    """Push a streaming chunk into LangGraph's custom stream.

    Must be called from within a running graph node — ``get_stream_writer``
    uses contextvars to find the active stream. Outside a node (e.g. unit
    tests that import the module), the writer is a no-op lambda and the
    call is silently dropped.
    """
    writer = get_stream_writer()
    writer({
        "kind": "stream_chunk",
        "node_id": node_id,
        "delta": delta,
        "meta": meta,
    })
