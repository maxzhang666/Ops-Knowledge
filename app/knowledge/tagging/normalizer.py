"""Spec 25 §4 — 标签规范化引擎。

normalize_tag(kb_id, raw, allow_create) 是写入路径的强制 chokepoint：
- user 标签 → allow_create=True，未命中字典则创建 canonical
- auto 标签 → allow_create=False，未命中则 drop
返回 canonical 字符串或 None。

字典查询用 redis 缓存（KB 级 hash map），避免每次 normalize 都查 PG。
任何字典写操作（create/rename/merge/delete/aliases 变更）必须主动 invalidate。
"""
from __future__ import annotations

import json
import uuid

import redis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.knowledge.tagging.models import TagDictionary

logger = structlog.get_logger(__name__)

CACHE_TTL_SECONDS = 3600  # 1h，字典变动时主动 invalidate


def _cache_key(kb_id: uuid.UUID | str) -> str:
    return f"kb_tag_dict:{kb_id}"


def _get_redis():
    try:
        return redis.from_url(settings.REDIS_URL)
    except Exception:
        return None  # redis 不可用时退化为直查 DB


def canonicalize_input(raw: str) -> str:
    """统一规范化输入字符串（lowercase / trim / 全角空格）。返回 '' 表示无效。"""
    if not raw:
        return ""
    s = raw.strip().lower().replace("　", " ").strip()
    return s


async def _load_dict_from_db(db: AsyncSession, kb_id: uuid.UUID) -> dict[str, str]:
    """加载 KB 字典：{lower_key: canonical}，canonical 自身和所有 aliases 都注册。"""
    rows = (await db.execute(
        select(TagDictionary).where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(False),
        )
    )).scalars().all()
    mapping: dict[str, str] = {}
    for r in rows:
        mapping[r.canonical.lower()] = r.canonical
        for a in (r.aliases or []):
            if isinstance(a, str):
                mapping[a.lower()] = r.canonical
    return mapping


async def get_kb_dict_map(db: AsyncSession, kb_id: uuid.UUID) -> dict[str, str]:
    """返回 KB 字典的 lower-key → canonical 映射；优先走 redis cache。"""
    rds = _get_redis()
    if rds is not None:
        try:
            cached = rds.get(_cache_key(kb_id))
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    mapping = await _load_dict_from_db(db, kb_id)
    if rds is not None:
        try:
            rds.setex(_cache_key(kb_id), CACHE_TTL_SECONDS, json.dumps(mapping))
        except Exception:
            pass
    return mapping


def invalidate_kb_dict_cache(kb_id: uuid.UUID | str) -> None:
    """字典写操作后调用 —— 删 KB cache，下次读重建。"""
    rds = _get_redis()
    if rds is None:
        return
    try:
        rds.delete(_cache_key(kb_id))
    except Exception:
        logger.warning("tag_dict_cache_invalidate_failed", kb_id=str(kb_id))


async def normalize_tags(
    db: AsyncSession,
    kb_id: uuid.UUID,
    raws: list[str],
    *,
    allow_create: bool,
    actor_id: uuid.UUID | None = None,
) -> list[str]:
    """批量规范化标签列表 —— 用户/自动两轨共用。

    allow_create=True (user 标签):
      未命中字典则创建新 canonical（用 raw.strip() 原大小写做 canonical 名）。
    allow_create=False (auto 标签):
      未命中则 drop。

    返回去重后的 canonical 列表（按输入顺序）。
    """
    if not raws:
        return []

    mapping = await get_kb_dict_map(db, kb_id)
    seen: set[str] = set()
    result: list[str] = []
    created_any = False

    for raw in raws:
        key = canonicalize_input(raw)
        if not key:
            continue
        canonical = mapping.get(key)
        if canonical is None:
            if not allow_create:
                continue  # auto-tag 未命中 drop
            # user 标签创建 canonical（保留输入的原大小写做显示）
            display = raw.strip().replace("　", " ").strip()
            if len(display) > 64:
                display = display[:64]
            new_row = TagDictionary(
                kb_id=kb_id,
                canonical=display,
                aliases=[],
                created_by=actor_id,
            )
            db.add(new_row)
            # 延迟 flush 由调用方 commit 触发；这里立即 flush 以便后续重复输入命中
            await db.flush()
            canonical = display
            mapping[key] = canonical
            created_any = True
            logger.info(
                "tag_dict.auto_created",
                kb_id=str(kb_id), canonical=canonical,
                actor=str(actor_id) if actor_id else None,
            )
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)

    if created_any:
        invalidate_kb_dict_cache(kb_id)

    return result
