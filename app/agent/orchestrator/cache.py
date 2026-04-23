"""In-memory rules cache (Plan 31 N3.4).

Routing 对每条 chat 都要 SELECT active rules —— 规则表 10+ 条且
Agent 对话量大时这一查询变显著。per-Agent 缓存活跃规则集，用
Agent.updated_at 做 invalidation 键（任何规则 CRUD / Agent config
edit 会 bump 该字段），不需要显式 cache.invalidate 调用散布在 service。

内存级缓存，进程内有效；多进程（Gunicorn workers / Celery）每个
worker 各自冷启动 —— 可接受，因为 routing 服务在 FastAPI 进程内，
而且 Agent.updated_at 天然分布一致。

限量：每 Agent 最多缓存 1 条记录；LRU 淘汰整体上限 256 条 Agent。
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_MAX_AGENTS_CACHED = 256


@dataclass
class _CacheEntry:
    updated_at: datetime
    rules: list[Any]  # list[AgentRule]


_lock = threading.Lock()
_cache: dict[uuid.UUID, _CacheEntry] = {}


def get_cached_rules(
    agent_id: uuid.UUID, agent_updated_at: datetime | None,
) -> list[Any] | None:
    """Return cached active rules if agent.updated_at matches our snapshot.

    updated_at 比对用 equality（而不是 ``>=``）—— 这是一个"版本号"
    而不是时间窗口。ORM refresh 可能把 updated_at 重置为之前的值
    （比如外部进程回滚），这种情况下我们仍然要 invalidate。
    """
    if agent_updated_at is None:
        return None
    with _lock:
        entry = _cache.get(agent_id)
        if entry is None:
            return None
        if entry.updated_at != agent_updated_at:
            _cache.pop(agent_id, None)
            return None
        return list(entry.rules)  # shallow copy — engine may mutate _classifier_result


def put_cached_rules(
    agent_id: uuid.UUID,
    agent_updated_at: datetime | None,
    rules: list[Any],
) -> None:
    if agent_updated_at is None:
        return
    with _lock:
        if len(_cache) >= _MAX_AGENTS_CACHED and agent_id not in _cache:
            # Simple FIFO eviction — routing traffic hits hot agents,
            # cold ones fall out naturally
            oldest_key = next(iter(_cache))
            _cache.pop(oldest_key, None)
        _cache[agent_id] = _CacheEntry(updated_at=agent_updated_at, rules=list(rules))


def invalidate(agent_id: uuid.UUID) -> None:
    """Explicit eviction; normally updated_at bump auto-invalidates, but
    call this after destructive rule ops (delete) where the Agent's
    updated_at itself doesn't change."""
    with _lock:
        _cache.pop(agent_id, None)


def clear_all() -> None:
    """Test-only reset."""
    with _lock:
        _cache.clear()
