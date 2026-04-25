import uuid

import structlog
import tiktoken
from celery import shared_task
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

try:
    _TOKEN_ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _TOKEN_ENC = None


def _count_tokens(text: str) -> int:
    if _TOKEN_ENC is None:
        return len(text) // 2
    return len(_TOKEN_ENC.encode(text, disallowed_special=()))

from app.core.config import settings
from app.core.runtime_config import get_sync_runtime_config
from app.knowledge.chunking.presets import get_strategy_for_preset
from app.knowledge.embedding.tasks import embed_document_chunks
from app.knowledge.ingestion.parser import parse_document
from app.knowledge.models import Chunk, Document, DocumentStatus, Folder, KnowledgeBase
from app.knowledge.storage.minio_service import MinIOService

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _update_progress(session, doc_id: str, stage: str, completed: int = 0, total: int = 0):
    session.execute(
        update(Document).where(Document.id == doc_id).values(
            processing_progress={"stage": stage, "completed": completed, "total": total}
        )
    )
    session.commit()


def _create_notification(session, user_id, doc_title: str, success: bool, doc_id: str, kb_id: str):
    from app.system.models import Notification
    # Link the notification to the KB (not the document) — there is no
    # per-document page in the frontend; clicking the notification should
    # take the user into the KB detail where they can find the document.
    notif = Notification(
        user_id=user_id,
        type="document_done",
        title=f"文档{'处理完成' if success else '处理失败'}: {doc_title}",
        content=f"{'文档已成功处理并建立索引' if success else '文档处理过程中出现错误，请检查'}",
        priority="normal" if success else "high",
        resource_type="knowledge_base",
        resource_id=uuid.UUID(kb_id) if isinstance(kb_id, str) else kb_id,
    )
    session.add(notif)


def _acquire_lock(doc_id: str, ttl: int = 1800) -> bool:
    """Redis SETNX lock for one-task-per-document."""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        return bool(r.set(f"doc_processing:{doc_id}", "1", nx=True, ex=ttl))
    except Exception:
        return True  # fallback: proceed if Redis unavailable


def _release_lock(doc_id: str):
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.delete(f"doc_processing:{doc_id}")
    except Exception:
        pass


PERMANENT_ERRORS = ("password", "encrypted", "empty", "content too short")


def _is_permanent_error(exc: Exception) -> bool:
    err_str = str(exc).lower()
    return any(keyword in err_str for keyword in PERMANENT_ERRORS)


def _emit_doc_event(
    name: str, doc_id, kb_id, status: str, error: str | None = None,
) -> None:
    """Celery tasks are sync; the event bus is async. Bridge via asyncio.run
    in a fresh loop to avoid contaminating the task's own state. Swallow any
    failure (Redis down etc.) — events are observation, never transactional.
    """
    import asyncio
    try:
        from app.integration.event_bus import publish
        from app.integration.events import Event

        async def _do():
            await publish(Event(
                name=name,  # type: ignore[arg-type]
                source="knowledge",
                data={
                    "document_id": str(doc_id),
                    "kb_id": str(kb_id),
                    "status": status,
                    **({"error": error} if error else {}),
                },
            ))

        asyncio.run(_do())
    except Exception as e:  # noqa: BLE001
        logger.warning("doc_event_emit_failed", name=name, doc_id=str(doc_id), error=str(e))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=240,
    retry_jitter=True,
    soft_time_limit=1800,
)
def process_document(self, doc_id: str) -> dict:
    if not _acquire_lock(doc_id):
        logger.info("document_already_processing", doc_id=doc_id)
        return {"status": "skipped", "message": "Already processing"}

    runtime_cfg = get_sync_runtime_config()
    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            doc = session.get(Document, doc_id)
            if doc is None:
                return {"status": "error", "message": "Document not found"}

            doc_user_id = doc.created_by
            doc_title = doc.title
            kb_id = str(doc.knowledge_base_id)

            session.execute(
                update(Document).where(Document.id == doc_id).values(status=DocumentStatus.PROCESSING)
            )
            session.commit()

            try:
                # API-ingested documents (spec 22.3) carry content inline in
                # metadata — skip MinIO download + parser, use text directly.
                meta = doc.metadata_ or {}
                if meta.get("_ingested_content"):
                    _update_progress(session, doc_id, "parsing")
                    text = str(meta["_ingested_content"])
                else:
                    # Stage 1: Download
                    _update_progress(session, doc_id, "downloading")
                    minio = MinIOService(runtime_cfg)
                    import asyncio
                    file_data = asyncio.run(minio.download(doc.file_path))

                    # Stage 2: Parse
                    _update_progress(session, doc_id, "parsing")
                    text = parse_document(file_data, doc.title)

                # Check for scanned PDF
                if len(text.strip()) < 50:
                    existing_meta = doc.metadata_ or {}
                    existing_meta["warning"] = "scan_suspected"
                    session.execute(
                        update(Document).where(Document.id == doc_id).values(metadata=existing_meta)
                    )
                    session.commit()

                if len(text.strip()) < 10:
                    session.execute(
                        update(Document).where(Document.id == doc_id).values(
                            status=DocumentStatus.ERROR,
                            error_message="Document content too short (< 10 chars after parsing)",
                        )
                    )
                    _create_notification(session, doc_user_id, doc_title, False, doc_id, kb_id)
                    session.commit()
                    return {"status": "error", "message": "Content too short"}

                # Stage 3: Chunking
                _update_progress(session, doc_id, "chunking")
                kb = session.get(KnowledgeBase, kb_id)
                from app.knowledge.chunking.config import ChunkingConfig
                cfg = ChunkingConfig.from_dict(kb.chunking_config if kb else None)

                strategy, params = get_strategy_for_preset(cfg.preset)

                # Custom mode: override params from chunking_config
                if cfg.chunk_size is not None:
                    params["chunk_size"] = cfg.chunk_size
                if cfg.chunk_overlap is not None:
                    params["chunk_overlap"] = cfg.chunk_overlap
                if cfg.delimiter:
                    params["delimiter"] = cfg.delimiter

                chunk_results = strategy.chunk(text, params)

                # Stage 3.5: Chunk enrichment (P24) — opt-in via chunking_config
                if cfg.needs_enrichment and chunk_results:
                    try:
                        from app.knowledge.chunking.enrichment import (
                            build_default_chat_fn, enrich_chunks_sync,
                        )
                        chat_fn = build_default_chat_fn()
                        enrichments = enrich_chunks_sync(
                            chunk_results, chat_fn,
                            want_keywords=cfg.auto_keywords,
                            want_questions=cfg.auto_questions,
                        )
                        for cr, eo in zip(chunk_results, enrichments):
                            if not eo.keywords and not eo.questions:
                                continue
                            meta = dict(cr.metadata or {})
                            if eo.keywords:
                                meta["keywords"] = eo.keywords
                            if eo.questions:
                                meta["questions"] = eo.questions
                            cr.metadata = meta
                    except Exception:
                        # 失败不阻断主流程 —— 降级为无 enrichment 继续索引
                        pass

                # Stage 4: Scoring + Save
                _update_progress(session, doc_id, "indexing", 0, len(chunk_results))
                from app.knowledge.quality.scorer import score_chunk

                # Build parent_chunk_id mapping: composite temporary IDs → real UUIDs
                parent_id_map: dict[str, uuid.UUID] = {}
                chunk_objects = []
                for i, cr in enumerate(chunk_results):
                    quality = score_chunk(cr.content)
                    chunk_id = uuid.uuid4()

                    real_parent_id = None
                    if cr.parent_chunk_id:
                        if cr.parent_chunk_id not in parent_id_map:
                            parent_id_map[cr.parent_chunk_id] = uuid.uuid4()
                        real_parent_id = parent_id_map[cr.parent_chunk_id]

                    token_est = _count_tokens(cr.content)
                    chunk_objects.append(Chunk(
                        id=chunk_id,
                        document_id=doc.id,
                        knowledge_base_id=doc.knowledge_base_id,
                        folder_id=doc.folder_id,
                        content=cr.content,
                        level=cr.level,
                        position=cr.position,
                        token_count=token_est,
                        quality_score=quality,
                        metadata_=cr.metadata or None,
                        parent_chunk_id=real_parent_id,
                    ))
                session.add_all(chunk_objects)

                from datetime import datetime, timezone
                session.execute(
                    update(Document).where(Document.id == doc_id).values(
                        status=DocumentStatus.COMPLETED,
                        chunk_count=len(chunk_objects),
                        token_count=sum(c.token_count for c in chunk_objects),
                        processed_at=datetime.now(timezone.utc),
                        processing_progress={"stage": "completed", "completed": len(chunk_objects), "total": len(chunk_objects)},
                    )
                )
                # Update KB-level chunk_count
                session.execute(
                    update(KnowledgeBase)
                    .where(KnowledgeBase.id == kb_id)
                    .values(chunk_count=KnowledgeBase.chunk_count + len(chunk_objects))
                )
                _create_notification(session, doc_user_id, doc_title, True, doc_id, kb_id)
                session.commit()

                # Cross-domain event — Langfuse / governance consumers listen
                # on the integration bus. Best-effort; swallow Redis failures
                # so the commit above stays authoritative.
                _emit_doc_event("document.completed", doc_id, kb_id, "COMPLETED")

                # Dispatch embedding task
                if kb and (kb.embedding_model_id or (kb.embedding_provider_id and kb.embedding_model_name)):
                    embed_document_chunks.delay(doc_id, kb_id)

                # E7: Invalidate L2 retrieval cache for this KB
                try:
                    import asyncio
                    from app.core.cache import CacheService
                    cache = CacheService()
                    asyncio.get_event_loop().run_until_complete(cache.invalidate_retrieval_kb(kb_id))
                    asyncio.get_event_loop().run_until_complete(cache.close())
                except Exception:
                    pass  # cache invalidation is best-effort

                logger.info("document_processed", doc_id=doc_id, chunk_count=len(chunk_objects))
                return {"status": "completed", "doc_id": doc_id, "chunk_count": len(chunk_objects)}

            except Exception as exc:
                session.rollback()
                err_str = str(exc)
                if "password" in err_str.lower() or "encrypted" in err_str.lower():
                    err_msg = "该文件有密码保护，请移除密码后重新上传"
                else:
                    err_msg = err_str[:1000]

                session.execute(
                    update(Document).where(Document.id == doc_id).values(
                        status=DocumentStatus.ERROR,
                        error_message=err_msg,
                    )
                )
                _create_notification(session, doc_user_id, doc_title, False, doc_id, kb_id)
                session.commit()

                _emit_doc_event("document.failed", doc_id, kb_id, "ERROR", error=err_msg)

                if _is_permanent_error(exc):
                    logger.warning("permanent_error_no_retry", doc_id=doc_id, error=err_msg)
                    return {"status": "error", "message": err_msg, "permanent": True}
                raise self.retry(exc=exc)

    finally:
        _release_lock(doc_id)
        engine.dispose()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=240,
    retry_jitter=True,
    soft_time_limit=1800,
)
def cascade_delete_kb(self, kb_id: str) -> dict:
    runtime_cfg = get_sync_runtime_config()
    engine = _get_sync_engine()
    try:
        # 1. Drop Milvus collection
        from app.knowledge.milvus.service import MilvusService
        milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
        collection_name = f"kb_{kb_id}"
        try:
            milvus_svc.drop_collection(collection_name)
            logger.info("milvus_collection_dropped", collection=collection_name)
        except Exception:
            logger.warning("milvus_collection_drop_skipped", collection=collection_name)

        # 2. Delete MinIO files
        minio = MinIOService(runtime_cfg)
        import asyncio
        deleted_files = asyncio.run(minio.delete_prefix(f"kb/{kb_id}/"))

        # 3. Delete PG data
        with Session(engine) as session:
            session.execute(delete(Document).where(Document.knowledge_base_id == kb_id))
            session.execute(delete(Folder).where(Folder.knowledge_base_id == kb_id))
            session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            session.commit()

        logger.info("kb_cascade_deleted", kb_id=kb_id, deleted_files=deleted_files)
        return {"status": "deleted", "kb_id": kb_id, "deleted_files": deleted_files}

    except Exception as exc:
        logger.error("kb_cascade_delete_failed", kb_id=kb_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        engine.dispose()
