import asyncio

import structlog
from celery import shared_task
from sqlalchemy import create_engine, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.runtime_config import get_sync_runtime_config
from app.knowledge.embedding.service import EmbeddingService
from app.knowledge.milvus.service import MilvusService
from app.knowledge.models import Chunk, Document, KnowledgeBase
from app.model.service import ModelService

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


def _get_sync_engine():
    return create_engine(SYNC_DB_URL, pool_pre_ping=True)


def _get_async_engine():
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)


def _collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=240,
    retry_jitter=True,
)
def embed_document_chunks(self, doc_id: str, kb_id: str) -> dict:
    runtime_cfg = get_sync_runtime_config()
    engine = _get_sync_engine()
    try:
        with Session(engine) as session:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                return {"status": "error", "message": "KB not found"}

            registry_id = kb.embedding_model_id
            provider_id = kb.embedding_provider_id
            model_name = kb.embedding_model_name
            if not registry_id and (not provider_id or not model_name):
                return {"status": "error", "message": "KB has no embedding config"}

            doc = session.get(Document, doc_id)
            if doc is None:
                return {"status": "error", "message": "Document not found"}

            chunks = session.scalars(
                select(Chunk)
                .where(Chunk.document_id == doc_id, Chunk.vector_id.is_(None))
                .order_by(Chunk.position)
            ).all()

            if not chunks:
                logger.info("embed_no_chunks", doc_id=doc_id)
                return {"status": "skipped", "message": "No chunks to embed"}

            chunk_dicts = [
                {
                    "id": c.id,
                    "content": c.content,
                    "document_id": c.document_id,
                    "folder_id": c.folder_id,
                    "level": c.level,
                    "position": c.position,
                    "title": doc.title,
                    "metadata": c.metadata_,
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
                        return await emb_svc.embed_and_store(
                            chunk_dicts, collection, registry_id=registry_id,
                        )
                    else:
                        dim = len(
                            (await model_svc.embed(provider_id, model_name, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(collection, dim)
                        return await emb_svc.embed_and_store(
                            chunk_dicts, collection, provider_id, model_name,
                        )
            finally:
                await a_engine.dispose()

        try:
            vector_ids = asyncio.run(_run_embed())
        finally:
            milvus_svc.close()

        # Update PG vector_ids
        with Session(engine) as session:
            for vid in vector_ids:
                session.execute(
                    update(Chunk).where(Chunk.id == vid).values(vector_id=vid)
                )
            session.commit()

        logger.info("embed_document_done", doc_id=doc_id, count=len(vector_ids))
        return {"status": "completed", "doc_id": doc_id, "embedded": len(vector_ids)}

    except Exception as exc:
        logger.error("embed_document_failed", doc_id=doc_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        engine.dispose()


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
                return {"status": "error", "message": "KB not found"}

            registry_id = kb.embedding_model_id
            provider_id = kb.embedding_provider_id
            model_name = kb.embedding_model_name
            if not registry_id and (not provider_id or not model_name):
                return {"status": "error", "message": "KB has no embedding config"}

            chunks = session.scalars(
                select(Chunk)
                .where(Chunk.knowledge_base_id == kb_id)
                .order_by(Chunk.position)
            ).all()

            if not chunks:
                return {"status": "skipped", "message": "No chunks to reindex"}

            docs = {
                str(d.id): d.title
                for d in session.scalars(
                    select(Document).where(Document.knowledge_base_id == kb_id)
                ).all()
            }

            chunk_dicts = [
                {
                    "id": c.id,
                    "content": c.content,
                    "document_id": c.document_id,
                    "folder_id": c.folder_id,
                    "level": c.level,
                    "position": c.position,
                    "title": docs.get(str(c.document_id), ""),
                    "metadata": c.metadata_,
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
                        return await emb_svc.embed_and_store(
                            chunk_dicts, new_collection, registry_id=registry_id,
                        )
                    else:
                        dim = len(
                            (await model_svc.embed(provider_id, model_name, ["dim_probe"]))[0]
                        )
                        milvus_svc.create_collection(new_collection, dim)
                        return await emb_svc.embed_and_store(
                            chunk_dicts, new_collection, provider_id, model_name,
                        )
            finally:
                await a_engine.dispose()

        try:
            vector_ids = asyncio.run(_run_reindex())

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
            session.commit()

        logger.info("reindex_kb_done", kb_id=kb_id, count=len(vector_ids))
        return {"status": "completed", "kb_id": kb_id, "reindexed": len(vector_ids)}

    except Exception as exc:
        logger.error("reindex_kb_failed", kb_id=kb_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        milvus_svc.close()
        engine.dispose()
