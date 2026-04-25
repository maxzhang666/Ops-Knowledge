"""Coverage Celery tasks — redundancy (M1) + topic distribution (T2).

Daily 扫描每个 active KB：从 Milvus 拉 dense_vector，运行矩阵相似度，
找到超阈值的 (a, b) 对写入 ``chunk_redundancy_pairs``。

保护性限制：
  * 每 KB 最大 chunk 数 ``MAX_CHUNKS_PER_KB``（默认 5000），超过跳过，
    避免内存炸裂；大库应在 future milestone 走 HNSW / ANN 扫描。
  * 每 KB 最多保留 ``MAX_PAIRS_PER_KB`` 条最高相似度对 —— 治理面板不
    需要全量，仅看代表性案例。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import numpy as np
import structlog
from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import sqlalchemy as sa

from app.core.config import settings
from app.knowledge.coverage.redundancy import (
    DEFAULT_THRESHOLD, RedundancyPair, find_redundant_pairs,
)

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
MAX_CHUNKS_PER_KB = 5000
MAX_PAIRS_PER_KB = 500


@shared_task(name="app.knowledge.coverage.tasks.redundancy_scan")
def redundancy_scan(kb_id: str | None = None) -> dict:
    """扫一个或全部 KB。返回统计摘要。"""
    from sqlalchemy import create_engine

    from app.knowledge.coverage.models import ChunkRedundancyPair
    from app.knowledge.embedding.tasks import _collection_name
    from app.knowledge.milvus.service import MilvusService
    from app.knowledge.models import Chunk, KnowledgeBase
    from app.core.runtime_config import get_sync_runtime_config

    runtime_cfg = get_sync_runtime_config()
    engine = create_engine(SYNC_DB_URL, pool_pre_ping=True)
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    totals = {"kbs": 0, "skipped": 0, "pairs": 0}
    try:
        with Session(engine) as session:
            if kb_id:
                kbs = session.scalars(
                    select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                ).all()
            else:
                kbs = session.scalars(
                    select(KnowledgeBase).where(KnowledgeBase.status == "active")
                ).all()

            for kb in kbs:
                totals["kbs"] += 1
                chunks = session.scalars(
                    select(Chunk).where(
                        Chunk.knowledge_base_id == kb.id,
                        Chunk.vector_id.isnot(None),
                    )
                ).all()
                if len(chunks) < 2:
                    totals["skipped"] += 1
                    continue
                if len(chunks) > MAX_CHUNKS_PER_KB:
                    logger.info(
                        "redundancy_scan_skip_too_large",
                        kb_id=str(kb.id), n=len(chunks), limit=MAX_CHUNKS_PER_KB,
                    )
                    totals["skipped"] += 1
                    continue

                collection = _collection_name(str(kb.id))
                if not milvus_svc.collection_exists(collection):
                    totals["skipped"] += 1
                    continue

                chunk_ids = [str(c.id) for c in chunks]
                vec_map = _fetch_vectors(milvus_svc, collection, chunk_ids)
                kept_ids: list[str] = []
                vectors_list: list[list[float]] = []
                for cid in chunk_ids:
                    vec = vec_map.get(cid)
                    if vec is None:
                        continue
                    kept_ids.append(cid)
                    vectors_list.append(vec)
                if len(kept_ids) < 2:
                    totals["skipped"] += 1
                    continue

                vectors = np.asarray(vectors_list, dtype=np.float32)
                pairs = find_redundant_pairs(
                    kept_ids, vectors, threshold=DEFAULT_THRESHOLD,
                )
                pairs = pairs[:MAX_PAIRS_PER_KB]

                # upsert —— 简化：先删本 KB，再写入，保证幂等
                session.execute(
                    delete(ChunkRedundancyPair).where(
                        ChunkRedundancyPair.kb_id == kb.id,
                    )
                )
                for p in pairs:
                    a, b = p.a_id, p.b_id
                    if a == b:
                        continue
                    # 确保 a < b 满足 check constraint
                    if a > b:
                        a, b = b, a
                    session.add(ChunkRedundancyPair(
                        kb_id=kb.id,
                        chunk_a_id=uuid.UUID(a),
                        chunk_b_id=uuid.UUID(b),
                        similarity=p.similarity,
                    ))
                totals["pairs"] += len(pairs)
                session.commit()
                logger.info(
                    "redundancy_scan_kb_done",
                    kb_id=str(kb.id), n=len(kept_ids), pairs=len(pairs),
                )
        return totals
    except Exception as exc:
        logger.exception("redundancy_scan_failed", error=str(exc))
        return {"status": "error", "message": str(exc)[:300], **totals}
    finally:
        milvus_svc.close()
        engine.dispose()


@shared_task(name="app.knowledge.coverage.tasks.topic_distribution_scan")
def topic_distribution_scan(kb_id: str | None = None) -> dict:
    """Plan 26 T2 — 对一个或全部 active KB 做话题聚类+LLM 标签。"""
    return asyncio.run(_run_topic_scan(kb_id))


async def _run_topic_scan(kb_id_filter: str | None) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.knowledge.coverage.models import KBTopic
    from app.knowledge.coverage.topics import (
        build_default_label_fn, build_topics, pick_topic_k,
    )
    from app.knowledge.embedding.tasks import _collection_name
    from app.knowledge.milvus.service import MilvusService
    from app.knowledge.models import Chunk, KnowledgeBase
    from app.core.runtime_config import get_sync_runtime_config

    runtime_cfg = get_sync_runtime_config()
    a_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(a_engine, class_=AsyncSession, expire_on_commit=False)
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    totals = {"kbs": 0, "topics": 0, "skipped": 0}
    try:
        async with sm() as db:
            if kb_id_filter:
                kbs = (await db.execute(
                    sa.select(KnowledgeBase).where(KnowledgeBase.id == kb_id_filter)
                )).scalars().all()
            else:
                kbs = (await db.execute(
                    sa.select(KnowledgeBase).where(KnowledgeBase.status == "active")
                )).scalars().all()

        label_fn = build_default_label_fn()

        for kb in kbs:
            totals["kbs"] += 1
            async with sm() as db:
                chunks = (await db.execute(
                    sa.select(Chunk.id, Chunk.content)
                    .where(
                        Chunk.knowledge_base_id == kb.id,
                        Chunk.vector_id.isnot(None),
                    )
                )).all()
            if len(chunks) < 6:
                totals["skipped"] += 1
                continue
            if len(chunks) > MAX_CHUNKS_PER_KB:
                logger.info("topic_scan_skip_too_large", kb_id=str(kb.id), n=len(chunks))
                totals["skipped"] += 1
                continue
            collection = _collection_name(str(kb.id))
            if not milvus_svc.collection_exists(collection):
                totals["skipped"] += 1
                continue

            chunk_ids = [str(r[0]) for r in chunks]
            content_map = {str(r[0]): (r[1] or "") for r in chunks}
            vec_map = _fetch_vectors(milvus_svc, collection, chunk_ids)
            kept_ids: list[str] = []
            vectors_list: list[list[float]] = []
            for cid in chunk_ids:
                v = vec_map.get(cid)
                if v is None:
                    continue
                kept_ids.append(cid)
                vectors_list.append(v)
            if len(kept_ids) < 6:
                totals["skipped"] += 1
                continue

            vectors = np.asarray(vectors_list, dtype=np.float32)
            contents = [content_map.get(cid, "") for cid in kept_ids]
            try:
                topics = await build_topics(
                    kept_ids, contents, vectors,
                    label_fn=label_fn, k=pick_topic_k(len(kept_ids)),
                )
            except Exception as exc:
                logger.warning("topic_build_failed", kb_id=str(kb.id), error=str(exc)[:200])
                topics = []

            async with sm() as db:
                await db.execute(
                    sa.delete(KBTopic).where(KBTopic.kb_id == kb.id)
                )
                for t in topics:
                    db.add(KBTopic(
                        kb_id=kb.id,
                        cluster_id=t.cluster_id,
                        label=t.label,
                        size=t.size,
                        keywords=t.keywords or None,
                        example_chunk_ids=t.example_chunk_ids or None,
                    ))
                await db.commit()
            totals["topics"] += len(topics)
            logger.info("topic_scan_kb_done", kb_id=str(kb.id), topics=len(topics))
        return totals
    finally:
        milvus_svc.close()
        await a_engine.dispose()


def _fetch_vectors(
    milvus_svc, collection: str, chunk_ids: list[str], batch: int = 500,
) -> dict[str, list[float]]:
    """分批拉 dense_vector（Milvus query 单次上限 1000 左右）。"""
    out: dict[str, list[float]] = {}
    for i in range(0, len(chunk_ids), batch):
        slab = chunk_ids[i : i + batch]
        try:
            rows = milvus_svc._client.query(
                collection_name=collection,
                filter=f"id in [{', '.join([repr(x) for x in slab])}]",
                output_fields=["id", "dense_vector"],
                limit=len(slab),
            )
        except Exception:
            logger.debug("milvus_query_slab_failed", exc_info=True)
            continue
        for r in rows:
            rid = r.get("id")
            vec = r.get("dense_vector")
            if rid and vec is not None:
                out[str(rid)] = list(vec)
    return out
