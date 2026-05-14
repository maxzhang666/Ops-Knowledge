import asyncio
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.runtime_config import get_sync_runtime_config
from app.knowledge.embedding.service import EmbeddingService
from app.knowledge.milvus.service import MilvusService, kb_collection_name
from app.knowledge.models import Chunk, Document, KnowledgeBase
from app.model.models import ModelRegistryEntry
from app.model.service import ModelService

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")  # psycopg v3


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _persist_model_dim(
    session: Session,
    registry_id: uuid.UUID | None,
    provider_id: uuid.UUID | None,
    model_name: str | None,
    dim: int,
) -> None:
    """First-time-set ModelRegistry.vector_dim（NULL → dim，不覆盖已有值）。

    供 Milvus 治理面板对账用：避免每次 overview 都 dim_probe。registry_id
    路径优先；无 registry_id 时按 (provider_id, model_id) 反查。"""
    if registry_id:
        session.execute(
            update(ModelRegistryEntry)
            .where(
                ModelRegistryEntry.id == registry_id,
                ModelRegistryEntry.vector_dim.is_(None),
            )
            .values(vector_dim=dim)
        )
    elif provider_id and model_name:
        session.execute(
            update(ModelRegistryEntry)
            .where(
                ModelRegistryEntry.provider_id == provider_id,
                ModelRegistryEntry.model_id == model_name,
                ModelRegistryEntry.vector_dim.is_(None),
            )
            .values(vector_dim=dim)
        )


def _get_async_engine():
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)


# Local alias kept for callers; canonical impl lives in milvus.service.
_collection_name = kb_collection_name


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=240,
    retry_jitter=True,
    name="app.knowledge.embedding.tasks.embed_unit_chunks",
)
def embed_unit_chunks(self, unit_type: str, unit_id: str, kb_id: str) -> dict:
    """Plan 41 M3.2 — 通用 embedding 任务。按 unit_type 路由查 unit
    (Document / KnowledgeEntry)，统一走 EmbeddingService 写 Milvus。"""
    runtime_cfg = get_sync_runtime_config()
    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                logger.warning("embed_skipped", kb_id=kb_id, unit_id=unit_id, reason="kb_not_found")
                return {"status": "error", "message": "KB not found"}

            registry_id = kb.embedding_model_id
            provider_id = kb.embedding_provider_id
            model_name = kb.embedding_model_name
            if not registry_id and (not provider_id or not model_name):
                logger.warning(
                    "embed_skipped", kb_id=kb_id, unit_id=unit_id,
                    reason="kb_has_no_embedding_config",
                )
                return {"status": "error", "message": "KB has no embedding config"}

            # M6.7 — KB 级 contextual prefix 阈值（默认 100；设 0 关闭 B）
            from app.knowledge.embedding.service import _CONTEXT_PREFIX_CHAR_THRESHOLD
            kb_chunking_cfg = kb.chunking_config or {}
            context_prefix_max_chars = int(
                kb_chunking_cfg.get(
                    "context_prefix_max_chars", _CONTEXT_PREFIX_CHAR_THRESHOLD,
                )
            )

            # 按 unit_type 取 unit 的 title（用于 chunk_dict 注入 + Milvus title 字段）
            unit_title: str
            if unit_type == "document":
                doc = session.get(Document, unit_id)
                if doc is None:
                    logger.warning("embed_skipped", kb_id=kb_id, unit_id=unit_id, reason="document_not_found")
                    return {"status": "error", "message": "Document not found"}
                unit_title = doc.title
            elif unit_type == "entry":
                from app.knowledge.models import KnowledgeEntry
                entry = session.get(KnowledgeEntry, unit_id)
                if entry is None:
                    logger.warning("embed_skipped", kb_id=kb_id, unit_id=unit_id, reason="entry_not_found")
                    return {"status": "error", "message": "Entry not found"}
                unit_title = entry.title
            else:
                logger.warning("embed_skipped", unit_type=unit_type, reason="unsupported_unit_type")
                return {"status": "error", "message": f"Unsupported unit_type: {unit_type}"}

            chunks = session.scalars(
                select(Chunk)
                .where(
                    Chunk.unit_type == unit_type,
                    Chunk.unit_id == unit_id,
                    Chunk.vector_id.is_(None),
                )
                .order_by(Chunk.position)
            ).all()

            if not chunks:
                logger.info("embed_no_chunks", unit_type=unit_type, unit_id=unit_id)
                return {"status": "skipped", "message": "No chunks to embed"}

            # Milvus schema 字段名仍用 "document_id"（历史兼容）。值取 unit_id
            # （任意 unit_type 的"识别 ID"），删除时按"document_id == unit_id"
            # filter 仍工作。Plan 40 P16 — 未来 Milvus schema 迁移时统一为 unit_id。
            chunk_dicts = [
                {
                    "id": c.id,
                    "content": c.content,
                    "document_id": c.unit_id,
                    "folder_id": c.folder_id,
                    "level": c.level,
                    "position": c.position,
                    "title": unit_title,
                    "metadata": c.metadata_,
                    # chunk_tags 仍写入 Milvus array column 供 L2/L4/L5 用；
                    # 但**不进** embedding 输入文本（见 _build_embedding_text 注释）
                    "chunk_tags": list(c.chunk_tags or []),
                }
                for c in chunks
            ]

        # Async embedding via ModelService + Milvus insert
        collection = _collection_name(kb_id)
        milvus_svc = MilvusService(runtime_cfg=runtime_cfg)

        async def _run_embed():
            a_engine = _get_async_engine()
            a_session = async_sessionmaker(a_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with a_session() as db:
                    model_svc = ModelService(db)
                    emb_svc = EmbeddingService(model_svc, milvus_svc)

                    if registry_id:
                        dim = len(
                            (await model_svc.embed_by_registry(registry_id, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(collection, dim)
                        vids = await emb_svc.embed_and_store(
                            chunk_dicts, collection, registry_id=registry_id,
                            context_prefix_max_chars=context_prefix_max_chars,
                        )
                        return vids, dim
                    else:
                        dim = len(
                            (await model_svc.embed(provider_id, model_name, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(collection, dim)
                        vids = await emb_svc.embed_and_store(
                            chunk_dicts, collection, provider_id, model_name,
                            context_prefix_max_chars=context_prefix_max_chars,
                        )
                        return vids, dim
            finally:
                await a_engine.dispose()

        try:
            vector_ids, embed_dim = asyncio.run(_run_embed())
        finally:
            milvus_svc.close()

        # Update PG vector_ids
        with Session(engine) as session:
            for vid in vector_ids:
                session.execute(
                    update(Chunk).where(Chunk.id == vid).values(vector_id=vid)
                )
            # Milvus 治理面板：首次 embed 时把维度回写 ModelRegistry，避免后续 overview 重复 dim_probe
            _persist_model_dim(session, registry_id, provider_id, model_name, embed_dim)
            # Plan 41 — entry 类型 unit 触发后置 status update（completed）
            if unit_type == "entry":
                from app.knowledge.models import KnowledgeEntry
                session.execute(
                    update(KnowledgeEntry)
                    .where(KnowledgeEntry.id == uuid.UUID(unit_id))
                    .values(status="completed", error_message=None)
                )
            session.commit()

        logger.info("embed_unit_done", unit_type=unit_type, unit_id=unit_id, count=len(vector_ids))

        # Spec 25 Plan B — entry 类型 embed 完成后链式触发 auto_tags 提取。
        # 提取 task 仅写 entry.auto_tags + chunks.chunk_tags（供 L2/L4/L5 用），
        # **不再 reset vector_id / 不触发二次 embed**（2026-05-14 §5.1 L1 局部回退）。
        if unit_type == "entry":
            try:
                from app.core.tasks import safe_delay
                from app.knowledge.tagging.extract_tasks import extract_auto_tags
                with Session(engine) as s_tag:
                    kb_tag = s_tag.get(KnowledgeBase, kb_id)
                    if kb_tag is None:
                        raise RuntimeError("kb vanished")
                    from app.knowledge.tagging.models import KBTagSettings
                    settings_row = s_tag.get(KBTagSettings, kb_tag.id)
                if settings_row is not None and settings_row.auto_tag_enabled:
                    safe_delay(extract_auto_tags, "entry", unit_id)
            except Exception:
                logger.debug(
                    "auto_tag_dispatch_failed",
                    unit_id=unit_id, exc_info=True,
                )

        # P24.M4 RAPTOR hook — 仅文件型支持（RAPTOR 假设 doc-level 层级树）
        if unit_type == "document":
            try:
                from app.knowledge.chunking.config import ChunkingConfig
                from app.knowledge.chunking.raptor_task import build_raptor_for_document
                from app.core.tasks import safe_delay

                with Session(engine) as s2:
                    kb2 = s2.get(KnowledgeBase, kb_id)
                    cfg = ChunkingConfig.from_dict(kb2.chunking_config if kb2 else None)
                if cfg.use_raptor:
                    safe_delay(build_raptor_for_document, unit_id, kb_id)
            except Exception:
                logger.debug("raptor_dispatch_failed", unit_id=unit_id, exc_info=True)

        return {
            "status": "completed",
            "unit_type": unit_type,
            "unit_id": unit_id,
            "embedded": len(vector_ids),
        }

    except Exception as exc:
        logger.error("embed_unit_failed", unit_type=unit_type, unit_id=unit_id, error=str(exc))
        # Plan 41 — entry 失败时记错误状态（best-effort，失败不阻塞 retry）
        if unit_type == "entry":
            try:
                from app.knowledge.models import KnowledgeEntry
                with Session(engine) as session:
                    session.execute(
                        update(KnowledgeEntry)
                        .where(KnowledgeEntry.id == uuid.UUID(unit_id))
                        .values(status="error", error_message=str(exc)[:500])
                    )
                    session.commit()
            except Exception:
                pass
        raise self.retry(exc=exc)
    finally:
        engine.dispose()


# ── 兼容 alias ───────────────────────────────────────────────────


@shared_task(name="app.knowledge.embedding.tasks.embed_document_chunks")
def embed_document_chunks(doc_id: str, kb_id: str) -> dict:
    """Plan 41 M3.2 — deprecated alias，转发到 embed_unit_chunks。
    保留任务名让旧 celery 队列里的待执行任务仍工作。新代码应直接调
    embed_unit_chunks(unit_type='document', unit_id=doc_id, kb_id=kb_id)。"""
    # bind=True 任务通过 celery 调用，这里直接 .apply 同步触发会冲突；
    # 简单转发到底层函数（self 不需要因 bind 是 task 装饰器层面）。
    from celery import current_app
    result = current_app.send_task(
        "app.knowledge.embedding.tasks.embed_unit_chunks",
        args=("document", doc_id, kb_id),
    )
    return {"status": "delegated", "task_id": result.id}


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    retry_backoff=True,
    retry_backoff_max=480,
    retry_jitter=True,
)
def reindex_kb(self, kb_id: str) -> dict:
    runtime_cfg = get_sync_runtime_config()
    engine = _get_sync_engine()
    milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
    try:
        with Session(engine) as session:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                logger.warning("reindex_skipped", kb_id=kb_id, reason="kb_not_found")
                return {"status": "error", "message": "KB not found"}

            registry_id = kb.embedding_model_id
            provider_id = kb.embedding_provider_id
            model_name = kb.embedding_model_name
            if not registry_id and (not provider_id or not model_name):
                logger.warning(
                    "reindex_skipped", kb_id=kb_id,
                    reason="kb_has_no_embedding_config",
                )
                return {"status": "error", "message": "KB has no embedding config"}

            chunks = session.scalars(
                select(Chunk)
                .where(Chunk.knowledge_base_id == kb_id)
                .order_by(Chunk.position)
            ).all()

            if not chunks:
                logger.info("reindex_skipped", kb_id=kb_id, reason="no_chunks_to_reindex")
                return {"status": "skipped", "message": "No chunks to reindex"}

            # Plan 40 M3 / 41 M3.2 — 多态：title 按 unit_type 分别从
            # documents / knowledge_entries 取。reindex 时 chunks 跨多种 unit_type 全扫
            from app.knowledge.models import KnowledgeEntry as _KE
            doc_titles = {
                str(d.id): d.title
                for d in session.scalars(
                    select(Document).where(Document.knowledge_base_id == kb_id)
                ).all()
            }
            entry_titles = {
                str(e.id): e.title
                for e in session.scalars(
                    select(_KE).where(_KE.knowledge_base_id == kb_id)
                ).all()
            }

            def _title_for(c: Chunk) -> str:
                if c.unit_type == "document":
                    return doc_titles.get(str(c.unit_id), "")
                if c.unit_type == "entry":
                    return entry_titles.get(str(c.unit_id), "")
                return ""

            chunk_dicts = [
                {
                    "id": c.id,
                    "content": c.content,
                    "document_id": c.unit_id,  # Milvus schema 字段名兼容
                    "folder_id": c.folder_id,
                    "level": c.level,
                    "position": c.position,
                    "title": _title_for(c),
                    "metadata": c.metadata_,
                    # chunk_tags 写入 Milvus 供 retrieval；不进 embedding 输入文本
                    "chunk_tags": list(c.chunk_tags or []),
                }
                for c in chunks
            ]

        old_collection = _collection_name(kb_id)
        new_collection = f"{old_collection}_new"

        async def _run_reindex():
            a_engine = _get_async_engine()
            a_session = async_sessionmaker(a_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with a_session() as db:
                    model_svc = ModelService(db)
                    emb_svc = EmbeddingService(model_svc, milvus_svc)

                    if registry_id:
                        dim = len(
                            (await model_svc.embed_by_registry(registry_id, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(new_collection, dim)
                        vids = await emb_svc.embed_and_store(
                            chunk_dicts, new_collection, registry_id=registry_id,
                        )
                        return vids, dim
                    else:
                        dim = len(
                            (await model_svc.embed(provider_id, model_name, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(new_collection, dim)
                        vids = await emb_svc.embed_and_store(
                            chunk_dicts, new_collection, provider_id, model_name,
                        )
                        return vids, dim
            finally:
                await a_engine.dispose()

        try:
            vector_ids, embed_dim = asyncio.run(_run_reindex())

            # Swap: drop old, rename new → old
            if milvus_svc.collection_exists(old_collection):
                milvus_svc.drop_collection(old_collection)
            milvus_svc._client.rename_collection(old_name=new_collection, new_name=old_collection)
        except Exception:
            # Cleanup new collection on failure
            if milvus_svc.collection_exists(new_collection):
                milvus_svc.drop_collection(new_collection)
            raise

        # Update PG vector_ids
        with Session(engine) as session:
            for vid in vector_ids:
                session.execute(
                    update(Chunk).where(Chunk.id == vid).values(vector_id=vid)
                )
            # Milvus 治理面板：reindex 后维度可能变（切了模型），强制写入最新维度
            if registry_id:
                session.execute(
                    update(ModelRegistryEntry)
                    .where(ModelRegistryEntry.id == registry_id)
                    .values(vector_dim=embed_dim)
                )
            elif provider_id and model_name:
                session.execute(
                    update(ModelRegistryEntry)
                    .where(
                        ModelRegistryEntry.provider_id == provider_id,
                        ModelRegistryEntry.model_id == model_name,
                    )
                    .values(vector_dim=embed_dim)
                )
            session.commit()

        logger.info("reindex_kb_done", kb_id=kb_id, count=len(vector_ids))

        # Cross-domain event — governance / Langfuse can listen.
        try:
            from app.integration.event_bus import publish
            from app.integration.events import Event

            async def _emit():
                await publish(Event(
                    name="kb.reindex_completed",
                    source="knowledge",
                    data={"kb_id": str(kb_id), "chunk_count": len(vector_ids)},
                ))
            asyncio.run(_emit())
        except Exception as e:  # noqa: BLE001
            logger.warning("reindex_event_emit_failed", kb_id=kb_id, error=str(e))

        return {"status": "completed", "kb_id": kb_id, "reindexed": len(vector_ids)}

    except Exception as exc:
        logger.error("reindex_kb_failed", kb_id=kb_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        milvus_svc.close()
        engine.dispose()
