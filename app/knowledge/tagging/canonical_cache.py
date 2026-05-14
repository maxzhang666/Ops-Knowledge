"""Spec 25 §5.3 — canonical embedding cache (L4 rerank boost 依赖)。

为 KB 字典的所有 canonical 预计算 embedding 向量，缓存在 redis（KB 级 hash）。
任何字典写操作（create / rename / merge / set_aliases / delete）必须触发 invalidate。

retrieval 路径调 get_kb_canonical_embeddings 拿 {canonical: vector} 字典，
与 query_vector 算 cosine 选 top-K relevant canonicals。

实现要点：
- 序列化 / 反序列化用 JSON（vector → list[float]）
- batch embed 一次性提交所有 canonicals，避免逐个 API 调用
- canonicals 上限 500（防字典爆炸场景下 embed 成本 / cache size 失控）
- 失败不抛 — retrieval 路径降级为不做 boost，仅记 logger
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import redis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.knowledge.models import KnowledgeBase
from app.knowledge.tagging.models import TagDictionary

logger = structlog.get_logger(__name__)

CACHE_TTL_SECONDS = 3600  # 1h
MAX_CANONICALS_TO_EMBED = 500  # cache 上限


def _cache_key(kb_id: uuid.UUID | str) -> str:
    return f"kb_canonical_emb:{kb_id}"


def _get_redis():
    try:
        return redis.from_url(settings.REDIS_URL)
    except Exception:
        return None


def invalidate_canonical_embeddings(kb_id: uuid.UUID | str) -> None:
    """字典任意写操作后调用 — 删 KB 级 canonical embedding cache。"""
    rds = _get_redis()
    if rds is None:
        return
    try:
        rds.delete(_cache_key(kb_id))
    except Exception:
        logger.warning(
            "canonical_emb_invalidate_failed",
            kb_id=str(kb_id), exc_info=True,
        )


async def _load_canonicals(db: AsyncSession, kb_id: uuid.UUID) -> list[str]:
    """字典 active canonicals（按 usage_count 倒序，取前 N）。"""
    rows = (await db.execute(
        select(TagDictionary.canonical, TagDictionary.usage_count)
        .where(
            TagDictionary.kb_id == kb_id,
            TagDictionary.is_deprecated.is_(False),
        )
        .order_by(TagDictionary.usage_count.desc())
        .limit(MAX_CANONICALS_TO_EMBED)
    )).all()
    return [r[0] for r in rows]


async def get_kb_canonical_embeddings(
    db: AsyncSession, kb_id: uuid.UUID, model_svc: Any,
) -> dict[str, list[float]]:
    """返回 KB 字典所有 canonical 的 embedding 字典；优先走 redis。

    cache miss 时：拉 canonicals → 调 embed_by_registry → 写 cache。
    任何失败（redis / DB / embed）退化为 {}，retrieval 路径自行降级跳过 boost。
    """
    rds = _get_redis()

    # 1. cache hit
    if rds is not None:
        try:
            cached = rds.get(_cache_key(kb_id))
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 2. miss — 拉 canonicals
    try:
        canonicals = await _load_canonicals(db, kb_id)
    except Exception:
        logger.warning("canonical_emb_load_failed", kb_id=str(kb_id), exc_info=True)
        return {}
    if not canonicals:
        return {}

    # 3. 拿 KB embedding registry
    kb = await db.get(KnowledgeBase, kb_id)
    registry_id = getattr(kb, "embedding_model_id", None) if kb else None
    if not registry_id:
        # KB 未配 embedding model → 不报错，跳过 boost
        return {}

    # 4. batch embed
    try:
        vectors = await model_svc.embed_by_registry(registry_id, canonicals)
    except Exception:
        logger.warning(
            "canonical_emb_compute_failed",
            kb_id=str(kb_id), count=len(canonicals), exc_info=True,
        )
        return {}
    if not vectors or len(vectors) != len(canonicals):
        return {}

    mapping = dict(zip(canonicals, [list(v) for v in vectors]))

    # 5. 写 cache（失败仅 logger）
    if rds is not None:
        try:
            rds.setex(_cache_key(kb_id), CACHE_TTL_SECONDS, json.dumps(mapping))
        except Exception:
            logger.warning(
                "canonical_emb_cache_write_failed",
                kb_id=str(kb_id), exc_info=True,
            )
    logger.info(
        "canonical_emb_computed",
        kb_id=str(kb_id), count=len(mapping),
    )
    return mapping
