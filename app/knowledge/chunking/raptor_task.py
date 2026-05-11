"""RAPTOR 构建 Celery 任务 (P24.M4).

触发条件：
  * 由 ``embedding/tasks.py::embed_document_chunks`` 在 L0 embed 完成后，
    依据 ``KB.chunking_config.use_raptor`` 决定是否派发。
  * 也可手动执行以重建整个 document 的 RAPTOR 层级。

执行步骤：
  1. 读目标文档所有 L0 chunk（带 ``vector_id``；从 Milvus 拉 embedding）
  2. 构建 RaptorSeed 列表
  3. 调 ``build_raptor_levels`` 生成各层 summary
  4. 在 PG 写入 summary 作为高层 Chunk（``level >= 1``；``metadata.raptor_children`` 列出成员 chunk id）
  5. 为这些新 chunk 执行 embedding + Milvus 入库（复用 EmbeddingService）

失败降级：任何阶段异常都记录日志并跳过（不影响 L0 检索的可用性）。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import numpy as np
import structlog
from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.chunking.config import ChunkingConfig
from app.knowledge.chunking.raptor import (
    RaptorSeed,
    build_default_embed_fn,
    build_default_summarize_fn,
    build_raptor_levels,
)

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")  # psycopg v3


@shared_task(name="app.knowledge.chunking.raptor_task.build_raptor_for_document")
def build_raptor_for_document(doc_id: str, kb_id: str) -> dict:
    from sqlalchemy import create_engine

    from app.knowledge.embedding.service import EmbeddingService
    from app.knowledge.embedding.tasks import _collection_name
    from app.knowledge.milvus.service import MilvusService
    from app.knowledge.models import Chunk, Document, KnowledgeBase
    from app.model.service import ModelService
    from app.core.runtime_config import get_sync_runtime_config

    runtime_cfg = get_sync_runtime_config()
    engine = create_engine(SYNC_DB_URL, pool_pre_ping=True)
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    try:
        with Session(engine) as session:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                return {"status": "error", "message": "KB not found"}
            cfg = ChunkingConfig.from_dict(kb.chunking_config)
            if not cfg.use_raptor:
                return {"status": "skipped", "message": "use_raptor is False"}

            doc = session.get(Document, doc_id)
            if doc is None:
                return {"status": "error", "message": "Document not found"}

            # Plan 40 M2 — 多态 unit FK 切读
            l0_chunks = session.scalars(
                select(Chunk)
                .where(
                    Chunk.unit_type == "document",
                    Chunk.unit_id == doc_id,
                    Chunk.level == 0,
                    Chunk.vector_id.isnot(None),
                )
                .order_by(Chunk.position)
            ).all()
            if len(l0_chunks) < 4:
                logger.info("raptor_too_few_chunks", doc_id=doc_id, n=len(l0_chunks))
                return {"status": "skipped", "message": "too few L0 chunks"}

            chunk_meta = [
                {"id": c.id, "content": c.content, "folder_id": c.folder_id}
                for c in l0_chunks
            ]

        # 从 Milvus 拉 L0 向量
        collection = _collection_name(kb_id)
        vec_map = _fetch_milvus_vectors(milvus_svc, collection, [str(c["id"]) for c in chunk_meta])
        seeds: list[RaptorSeed] = []
        for c in chunk_meta:
            vec = vec_map.get(str(c["id"]))
            if vec is None:
                continue
            seeds.append(RaptorSeed(
                id=c["id"],
                content=c["content"],
                embedding=np.asarray(vec, dtype=float),
            ))
        if len(seeds) < 4:
            logger.info("raptor_no_vectors", doc_id=doc_id)
            return {"status": "skipped", "message": "no vectors"}

        summarize_fn = build_default_summarize_fn()
        embed_fn = build_default_embed_fn(uuid.UUID(str(kb_id)))
        # asyncio.Runner (PY 3.11+) drains pending tasks (httpx
        # AsyncClient.aclose, etc.) BEFORE closing the loop. Plain
        # asyncio.run() schedules close coroutines but tears down the
        # loop before they get a chance to run, producing harmless but
        # noisy "RuntimeError: Event loop is closed" tracebacks in the
        # worker log after every RAPTOR run.
        with asyncio.Runner() as runner:
            summaries = runner.run(build_raptor_levels(
                seeds,
                summarize_fn=summarize_fn,
                embed_fn=embed_fn,
                max_levels=cfg.raptor_max_levels,
            ))
        if not summaries:
            return {"status": "noop", "message": "no summaries produced"}

        # 写 L>=1 chunk 到 PG
        with Session(engine) as session:
            doc = session.get(Document, doc_id)
            if doc is None:
                return {"status": "error", "message": "Document gone mid-run"}
            base_pos = len(l0_chunks)
            chunk_rows = []
            for i, s in enumerate(summaries):
                meta = {"raptor_children": [str(m) for m in s.member_ids]}
                chunk_rows.append(Chunk(
                    id=s.id,
                    # Plan 40 M3 — document_id 已 drop
                    unit_type="document",
                    unit_id=doc.id,
                    knowledge_base_id=doc.knowledge_base_id,
                    folder_id=doc.folder_id,
                    content=s.summary,
                    level=s.level,
                    position=base_pos + i,
                    token_count=len(s.summary) // 3,
                    metadata_=meta,
                ))
            session.add_all(chunk_rows)
            session.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.id == kb_id)
                .values(chunk_count=KnowledgeBase.chunk_count + len(chunk_rows))
            )
            session.commit()

        # 对新 chunk 执行 embedding + Milvus 入库
        _embed_summary_chunks(
            milvus_svc, collection, runtime_cfg,
            [
                {
                    "id": s.id,
                    "content": s.summary,
                    "document_id": uuid.UUID(str(doc_id)),
                    "folder_id": None,
                    "level": s.level,
                    "position": base_pos + i,
                    "title": "",
                    "metadata": {"raptor_children": [str(m) for m in s.member_ids]},
                }
                for i, s in enumerate(summaries)
            ],
            kb_id,
        )
        logger.info("raptor_build_done", doc_id=doc_id, summaries=len(summaries))
        return {"status": "completed", "summaries": len(summaries)}
    except Exception as exc:
        logger.exception("raptor_build_failed", doc_id=doc_id, error=str(exc))
        return {"status": "error", "message": str(exc)[:300]}
    finally:
        milvus_svc.close()
        engine.dispose()


def _fetch_milvus_vectors(milvus_svc, collection: str, chunk_ids: list[str]) -> dict[str, list[float]]:
    """批量拉 dense_vector（sparse 不用）—— chunk_id 作为主键查询。"""
    if not chunk_ids:
        return {}
    try:
        rows = milvus_svc._client.query(
            collection_name=collection,
            filter=f"id in [{', '.join([repr(x) for x in chunk_ids])}]",
            output_fields=["id", "dense_vector"],
            limit=len(chunk_ids),
        )
    except Exception:
        logger.debug("milvus_query_failed", collection=collection, exc_info=True)
        return {}
    out: dict[str, list[float]] = {}
    for r in rows:
        rid = r.get("id")
        vec = r.get("dense_vector")
        if rid and vec is not None:
            out[str(rid)] = list(vec)
    return out


def _embed_summary_chunks(milvus_svc, collection: str, runtime_cfg, chunk_dicts: list[dict], kb_id: str) -> None:
    """对 RAPTOR 生成的高层 chunk 执行 embed + Milvus 入库。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.knowledge.embedding.service import EmbeddingService
    from app.knowledge.models import Chunk, KnowledgeBase
    from app.model.service import ModelService

    async def _run():
        a_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            async with async_sessionmaker(a_engine, class_=AsyncSession, expire_on_commit=False)() as db:
                kb = await db.get(KnowledgeBase, kb_id)
                if kb is None:
                    return
                model_svc = ModelService(db)
                emb_svc = EmbeddingService(model_svc, milvus_svc)
                if kb.embedding_model_id:
                    await emb_svc.embed_and_store(
                        chunk_dicts, collection, registry_id=kb.embedding_model_id,
                    )
                elif kb.embedding_provider_id and kb.embedding_model_name:
                    await emb_svc.embed_and_store(
                        chunk_dicts, collection, kb.embedding_provider_id, kb.embedding_model_name,
                    )
        finally:
            await a_engine.dispose()

    asyncio.run(_run())

    # 回写 vector_id
    from sqlalchemy import create_engine
    engine = create_engine(SYNC_DB_URL, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            from app.knowledge.models import Chunk as _Chunk
            for c in chunk_dicts:
                session.execute(
                    update(_Chunk).where(_Chunk.id == c["id"]).values(vector_id=str(c["id"]))
                )
            session.commit()
    finally:
        engine.dispose()
