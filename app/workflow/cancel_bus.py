"""Cross-worker cancellation via Redis Pub/Sub.

Plan 15's cancel endpoint only reaches tasks on the current worker. This
module fans out cancellation to all workers: each subscribes to a channel,
compares incoming execution_id against its local ``_live_tasks``, and
invokes ``task.cancel()`` on match.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import redis.asyncio as aioredis

from app.core.config import settings

log = logging.getLogger(__name__)
CANCEL_CHANNEL = "workflow:cancel"


async def publish_cancel(execution_id: uuid.UUID) -> None:
    """Fire-and-forget — never raise on Redis issues; caller has already
    updated DB state so the cancel is at least persisted there."""
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await r.publish(CANCEL_CHANNEL, str(execution_id))
        await r.aclose()
    except Exception as e:  # noqa: BLE001
        log.warning("cancel_bus publish failed: %s", e)


async def start_cancel_subscriber(live_tasks: dict) -> asyncio.Task:
    async def _loop() -> None:
        while True:
            try:
                r = aioredis.from_url(settings.REDIS_URL)
                pubsub = r.pubsub()
                await pubsub.subscribe(CANCEL_CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    raw = msg["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        eid = uuid.UUID(str(raw))
                    except ValueError:
                        continue
                    task = live_tasks.get(eid)
                    if task is not None and not task.done():
                        log.info("cancel_bus: cancelling local execution %s", eid)
                        task.cancel()
            except Exception as e:  # noqa: BLE001
                log.warning("cancel_bus subscriber crashed, retrying: %s", e)
                await asyncio.sleep(2)

    return asyncio.create_task(_loop())
