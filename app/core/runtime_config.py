"""Runtime configuration: system_settings JSONB with env fallback.

Cache invalidation is triggered two ways:
1. Time-based TTL (fallback if Pub/Sub is unreachable).
2. Redis Pub/Sub channel ``runtime_config:invalidate`` — every process
   (web worker, Celery worker) subscribes on startup and clears its cache
   when a message is received.
"""
import asyncio
import threading
import time

import structlog

logger = structlog.get_logger(__name__)

_cache: dict | None = None
_cache_ts: float = 0
_CACHE_TTL = 60  # seconds

_PUBSUB_CHANNEL = "runtime_config:invalidate"


async def get_runtime_config(db) -> dict:
    """Read system_settings row 1; returns cached copy within TTL."""
    global _cache, _cache_ts

    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        from app.system.models import SystemSettings
        row = await db.get(SystemSettings, 1)
        _cache = row.settings if row else {}
        _cache_ts = now
    except Exception:
        logger.debug("runtime_config_load_failed", exc_info=True)
        _cache = {}
        _cache_ts = now

    return _cache


def get_sync_runtime_config() -> dict:
    """Sync version for Celery tasks. Creates a disposable DB connection."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings

    # Use psycopg v3 (already installed via requirements.txt). psycopg2 is
    # NOT in the env — converting to "+psycopg2" raises ModuleNotFoundError.
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    try:
        with Session(engine) as session:
            from app.system.models import SystemSettings
            row = session.get(SystemSettings, 1)
            return row.settings if row else {}
    except Exception:
        logger.debug("sync_runtime_config_load_failed", exc_info=True)
        return {}
    finally:
        engine.dispose()


def invalidate_cache() -> None:
    """Force next access to re-read from DB."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0


def resolve(runtime: dict, section: str, key: str, env_fallback):
    """runtime_config[section][key] -> env_fallback."""
    return runtime.get(section, {}).get(key, env_fallback)


def publish_invalidate() -> None:
    """Broadcast cache invalidation to all processes. Fail-open on Redis error."""
    try:
        import redis

        from app.core.config import settings
        r = redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
        r.publish(_PUBSUB_CHANNEL, "invalidate")
    except Exception:
        logger.debug("runtime_config_publish_failed", exc_info=True)


async def _async_subscribe_loop() -> None:
    """Asyncio loop: subscribe and invalidate on each message.

    Must handle asyncio.CancelledError cleanly to avoid
    'Task was destroyed but it is pending' on shutdown/reload.
    """
    import redis.asyncio as aredis

    from app.core.config import settings
    client = None
    pubsub = None
    try:
        while True:
            try:
                client = aredis.from_url(
                    settings.REDIS_URL,
                    socket_keepalive=True,
                    health_check_interval=30,
                )
                pubsub = client.pubsub()
                await pubsub.subscribe(_PUBSUB_CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        invalidate_cache()
                        logger.info("runtime_config_cache_invalidated_via_pubsub")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("runtime_config_subscribe_error", exc_info=True)
                await asyncio.sleep(5)  # backoff then reconnect
    except asyncio.CancelledError:
        pass  # clean shutdown
    finally:
        try:
            if pubsub is not None:
                await pubsub.unsubscribe(_PUBSUB_CHANNEL)
                await pubsub.close()
            if client is not None:
                await client.aclose()
        except Exception:
            pass


def start_async_subscriber(loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task | None:
    """Start the subscribe loop as an asyncio background task (FastAPI startup)."""
    try:
        loop = loop or asyncio.get_event_loop()
        return loop.create_task(_async_subscribe_loop())
    except Exception:
        logger.debug("runtime_config_async_subscriber_failed", exc_info=True)
        return None


def _sync_subscribe_loop() -> None:
    """Thread loop: subscribe and invalidate (for Celery workers).

    PubSub is a long-lived blocking read; ``socket_timeout`` MUST be None,
    otherwise ``listen()`` raises ``TimeoutError`` every N seconds when no
    messages flow. Liveness is preserved via ``health_check_interval``
    (server-side PING) + ``socket_keepalive`` (TCP-level) so dead
    connections are detected without aborting idle reads.
    """
    import redis

    from app.core.config import settings
    while True:
        try:
            client = redis.from_url(
                settings.REDIS_URL,
                socket_keepalive=True,
                health_check_interval=30,
            )
            pubsub = client.pubsub()
            pubsub.subscribe(_PUBSUB_CHANNEL)
            for msg in pubsub.listen():
                if msg.get("type") == "message":
                    invalidate_cache()
                    logger.info("runtime_config_cache_invalidated_via_pubsub")
        except Exception:
            logger.warning("runtime_config_subscribe_error", exc_info=True)
            time.sleep(5)


def start_sync_subscriber() -> threading.Thread | None:
    """Start the subscribe loop in a daemon thread (Celery worker startup)."""
    try:
        t = threading.Thread(target=_sync_subscribe_loop, daemon=True, name="runtime-config-sub")
        t.start()
        return t
    except Exception:
        logger.debug("runtime_config_sync_subscriber_failed", exc_info=True)
        return None
