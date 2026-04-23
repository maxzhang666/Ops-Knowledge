"""Redis Pub/Sub event bus — best-effort publish, register handlers at import.

Publishers must never block on delivery. If Redis is down the publish call
logs and returns. Callers are responsible for their own state persistence
(DB rows, state machines) — events are observation, not transactions.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import redis.asyncio as aioredis

from app.core.config import settings
from app.integration.events import CHANNEL, Event

log = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]

_handlers: dict[str, list[Handler]] = {}


def on(event_name: str):
    """Register an async handler for a specific event name."""
    def wrap(func: Handler) -> Handler:
        _handlers.setdefault(event_name, []).append(func)
        return func
    return wrap


def clear_handlers() -> None:
    """Test utility."""
    _handlers.clear()


def registered_handlers(event_name: str) -> list[Handler]:
    return list(_handlers.get(event_name, []))


async def publish(event: Event) -> None:
    """Best-effort publish. Never raises."""
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await r.publish(CHANNEL, event.model_dump_json())
        await r.aclose()
    except Exception as e:  # noqa: BLE001
        log.warning("event_bus publish failed (%s): %s", event.name, e)


async def dispatch(event: Event) -> None:
    """Invoke all registered handlers for an event. Used by the subscriber,
    also directly testable."""
    for h in _handlers.get(event.name, []):
        try:
            await h(event)
        except Exception:  # noqa: BLE001
            log.exception("handler for %s failed", event.name)


async def start_subscriber() -> asyncio.Task:
    async def _loop() -> None:
        while True:
            try:
                r = aioredis.from_url(settings.REDIS_URL)
                pubsub = r.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    raw = msg["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        event = Event.model_validate_json(raw)
                    except Exception as e:  # noqa: BLE001
                        log.warning("event_bus bad payload: %s / %s", e, str(raw)[:200])
                        continue
                    await dispatch(event)
            except Exception as e:  # noqa: BLE001
                log.warning("event_bus subscriber crashed, retrying: %s", e)
                await asyncio.sleep(2)

    return asyncio.create_task(_loop())
