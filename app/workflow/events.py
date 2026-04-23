"""Execution event bus — scheduler fans out to WebSocket / logger / Langfuse.

Non-critical events (stream_chunk, node_output, heartbeat) are dropped on
full-queue — scheduler MUST NOT block on slow consumers. Critical events
(workflow_start, workflow_end, node_error) use a bounded wait so clients
don't miss state transitions and end up "still running" forever.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

log = logging.getLogger(__name__)

EventType = Literal[
    "workflow_start", "workflow_end",
    "node_start", "node_output", "node_error", "node_end",
    "stream_chunk", "heartbeat",
    # HITL: graph paused on a human_approval node. Payload includes the
    # prompt + approver roles so the frontend can surface a modal.
    "waiting_input",
]


_CRITICAL_EVENT_TYPES: frozenset[str] = frozenset({
    "workflow_start", "workflow_end", "node_error",
})


@dataclass
class Event:
    type: EventType
    execution_id: str
    node_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    def __init__(
        self,
        queue_size: int = 256,
        critical_wait: float = 1.0,
        history_size: int = 256,
    ) -> None:
        self._subs: list[asyncio.Queue[Event | None]] = []
        self._closed = False
        self._queue_size = queue_size
        self._critical_wait = critical_wait
        # Keep the full stream so subscribers that connect AFTER the scheduler
        # has finished (common for fast-fail workflows) still see what
        # happened. Otherwise a workflow that crashes in validate appears as
        # silence to the UI.
        self._history: list[Event] = []
        self._history_max = history_size

    def subscribe(self) -> asyncio.Queue[Event | None]:
        q: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=self._queue_size)
        # Replay buffered history so late subscribers catch up.
        for ev in self._history:
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                break
        # If the bus has already closed, push the sentinel so stream() exits
        # cleanly once history drains.
        if self._closed:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self._subs.append(q)
        return q

    async def publish(self, ev: Event) -> None:
        # Record in history even if already closed — lets us replay the tail
        # to very-late subscribers (router keeps bus alive briefly after
        # close; see _run_and_cleanup).
        self._history.append(ev)
        if len(self._history) > self._history_max:
            del self._history[: len(self._history) - self._history_max]
        if self._closed:
            return
        critical = ev.type in _CRITICAL_EVENT_TYPES
        for q in list(self._subs):
            if critical:
                try:
                    await asyncio.wait_for(q.put(ev), timeout=self._critical_wait)
                except asyncio.TimeoutError:
                    log.warning("Dropped critical event %s on slow subscriber", ev.type)
            else:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    pass  # drop — best effort

    async def close(self) -> None:
        self._closed = True
        for q in self._subs:
            try:
                q.put_nowait(None)  # sentinel: end-of-stream
            except asyncio.QueueFull:
                pass

    async def stream(self, q: asyncio.Queue[Event | None]) -> AsyncIterator[Event]:
        while True:
            ev = await q.get()
            if ev is None:
                return
            yield ev
