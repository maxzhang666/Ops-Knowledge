import hashlib
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

L1_PREFIX = "l1:"
L2_PREFIX = "l2:"
L3_PREFIX = "l3:"

L1_TTL = 300       # 5 min  — hot data (settings, user prefs)
L2_TTL = 600       # 10 min — retrieval results
L3_TTL = 3600      # 1 hr   — embedding vectors


def _hash_key(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CacheService:
    def __init__(self, redis_url: str | None = None):
        self._url = redis_url or settings.REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def _conn(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    # ── L1: Hot data ─────────────────────────────────────────────

    async def get_hot(self, *key_parts: str) -> Any | None:
        r = await self._conn()
        val = await r.get(L1_PREFIX + _hash_key(*key_parts))
        return json.loads(val) if val else None

    async def set_hot(self, value: Any, *key_parts: str) -> None:
        r = await self._conn()
        await r.set(L1_PREFIX + _hash_key(*key_parts), json.dumps(value), ex=L1_TTL)

    async def invalidate_hot(self, *key_parts: str) -> None:
        r = await self._conn()
        await r.delete(L1_PREFIX + _hash_key(*key_parts))

    # ── L2: Retrieval results ────────────────────────────────────

    async def get_retrieval(self, *key_parts: str) -> Any | None:
        r = await self._conn()
        val = await r.get(L2_PREFIX + _hash_key(*key_parts))
        return json.loads(val) if val else None

    async def set_retrieval(self, value: Any, *key_parts: str) -> None:
        r = await self._conn()
        await r.set(L2_PREFIX + _hash_key(*key_parts), json.dumps(value), ex=L2_TTL)

    async def invalidate_retrieval_kb(self, kb_id: str) -> None:
        r = await self._conn()
        async for key in r.scan_iter(match=f"{L2_PREFIX}*"):
            await r.delete(key)

    # ── L3: Embedding cache ──────────────────────────────────────

    async def get_embedding(self, *key_parts: str) -> Any | None:
        r = await self._conn()
        val = await r.get(L3_PREFIX + _hash_key(*key_parts))
        return json.loads(val) if val else None

    async def set_embedding(self, value: Any, *key_parts: str) -> None:
        r = await self._conn()
        await r.set(L3_PREFIX + _hash_key(*key_parts), json.dumps(value), ex=L3_TTL)
