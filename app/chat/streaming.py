from __future__ import annotations

import json
from collections.abc import AsyncGenerator


def sse_event(event: str, data: dict | str) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_chat_response(
    pipeline_generator: AsyncGenerator[tuple[str, dict | str], None],
) -> AsyncGenerator[str, None]:
    """Wrap pipeline generator into SSE-formatted string stream."""
    async for event_type, data in pipeline_generator:
        yield sse_event(event_type, data)
