"""Spec 25 — 字典治理异步回填 + 每日 usage_count 重算。

celery 任务三件：
- backfill_tag_rename: 字典 canonical 改名后，重写所有 entries.tags + chunks.chunk_tags
- backfill_tag_merge: sources canonical 合并到 target 后，重写所有受影响行
- rebuild_tag_dictionary_stats: daily beat，全表重算 usage_count（avoid hot-path writes）
"""
from __future__ import annotations

import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.models import Chunk, KnowledgeEntry
from app.knowledge.tagging.models import TagDictionary

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _invalidate_kb_cache(kb_id: str) -> None:
    """回填完成后强制 invalidate 两层缓存（dict lookup + canonical embeddings）。"""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.delete(f"kb_tag_dict:{kb_id}")
        r.delete(f"kb_canonical_emb:{kb_id}")
    except Exception:
        logger.warning("tag_dict_cache_invalidate_failed", kb_id=kb_id, exc_info=True)


def _rewrite_tag(tag_list: list[str] | None, mapping: dict[str, str]) -> tuple[list[str] | None, bool]:
    """把 tag_list 里出现的 old_canonical 替换成 new_canonical，去重保序。
    返回 (new_list_or_None, changed)。"""
    if not tag_list:
        return tag_list, False
    seen: set[str] = set()
    out: list[str] = []
    changed = False
    for t in tag_list:
        new_t = mapping.get(t, t)
        if new_t != t:
            changed = True
        if new_t and new_t not in seen:
            seen.add(new_t)
            out.append(new_t)
    return (out or None), changed


@shared_task(
    bind=True,
    name="app.knowledge.tagging.tasks.backfill_tag_rename",
    max_retries=2,
    default_retry_delay=60,
)
def backfill_tag_rename(self, kb_id: str, old_canonical: str, new_canonical: str) -> dict:
    """字典 canonical 改名 → 重写所有 entries.tags + chunks.chunk_tags。"""
    mapping = {old_canonical: new_canonical}
    return _backfill_kb(kb_id, mapping, op="rename")


@shared_task(
    bind=True,
    name="app.knowledge.tagging.tasks.backfill_tag_merge",
    max_retries=2,
    default_retry_delay=60,
)
def backfill_tag_merge(self, kb_id: str, source_canonicals: list[str], target_canonical: str) -> dict:
    """字典合并 → 所有 source canonical 重写为 target。"""
    mapping = {src: target_canonical for src in source_canonicals}
    return _backfill_kb(kb_id, mapping, op="merge")


def _backfill_kb(kb_id: str, mapping: dict[str, str], *, op: str) -> dict:
    """共享回填逻辑：扫描 entries / chunks，按 mapping 重写并 commit。"""
    if not mapping:
        return {"status": "skipped", "reason": "empty_mapping"}

    engine = _get_sync_engine()
    rewritten_entries = 0
    rewritten_chunks = 0
    try:
        with Session(engine) as session:
            kb_uuid = uuid.UUID(kb_id)
            # 1. entries.tags 重写
            entries = session.execute(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.knowledge_base_id == kb_uuid,
                )
            ).scalars().all()
            for e in entries:
                new_tags, changed = _rewrite_tag(e.tags, mapping)
                if changed:
                    e.tags = new_tags
                    rewritten_entries += 1
            # 2. chunks.chunk_tags 重写
            chunks = session.execute(
                select(Chunk).where(Chunk.knowledge_base_id == kb_uuid)
            ).scalars().all()
            for c in chunks:
                new_tags, changed = _rewrite_tag(c.chunk_tags, mapping)
                if changed:
                    c.chunk_tags = new_tags
                    rewritten_chunks += 1
            session.commit()
    finally:
        engine.dispose()
        _invalidate_kb_cache(kb_id)

    logger.info(
        "tag_backfill_done",
        op=op, kb_id=kb_id,
        rewritten_entries=rewritten_entries,
        rewritten_chunks=rewritten_chunks,
    )
    return {
        "status": "completed",
        "op": op,
        "kb_id": kb_id,
        "rewritten_entries": rewritten_entries,
        "rewritten_chunks": rewritten_chunks,
    }


@shared_task(
    bind=True,
    name="app.knowledge.tagging.tasks.rebuild_tag_dictionary_stats",
)
def rebuild_tag_dictionary_stats(self) -> dict:
    """每日 beat：全表重算 tag_dictionary.usage_count。

    avoid hot-path counter updates；统计上限按 entries.tags 数组中 canonical
    出现次数（chunks.chunk_tags 是 entries.tags 派生，重复计数无意义）。
    """
    engine = _get_sync_engine()
    updated = 0
    try:
        with Session(engine) as session:
            dicts = session.execute(select(TagDictionary)).scalars().all()
            entries = session.execute(
                select(KnowledgeEntry.knowledge_base_id, KnowledgeEntry.tags)
            ).all()
            # 按 KB 聚合 tag 计数
            kb_counts: dict[uuid.UUID, dict[str, int]] = {}
            for kb_id, tags in entries:
                if not tags:
                    continue
                bucket = kb_counts.setdefault(kb_id, {})
                for t in tags:
                    if isinstance(t, str):
                        bucket[t] = bucket.get(t, 0) + 1
            for d in dicts:
                count = kb_counts.get(d.kb_id, {}).get(d.canonical, 0)
                if d.usage_count != count:
                    session.execute(
                        update(TagDictionary)
                        .where(TagDictionary.id == d.id)
                        .values(usage_count=count)
                    )
                    updated += 1
            session.commit()
    finally:
        engine.dispose()

    logger.info("tag_dict_stats_rebuild_done", updated=updated)
    return {"status": "completed", "updated": updated}
