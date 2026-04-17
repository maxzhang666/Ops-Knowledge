import shutil
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update

from app.core.celery import celery_app
from app.core.config import settings
from app.core.runtime_config import get_sync_runtime_config
from app.knowledge.models import Document, DocumentStatus, KBStatus, KnowledgeBase

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.system.tasks.disk_space_monitor")
def disk_space_monitor():
    """E11: Monitor disk space and create notification if below threshold."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    usage = shutil.disk_usage("/")
    free_pct = usage.free / usage.total * 100

    if free_pct < 10:
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
        engine = create_engine(sync_url)
        try:
            with Session(engine) as session:
                from app.system.models import Notification
                notif = Notification(
                    user_id=None,  # system-level
                    type="quota_warning",
                    title="磁盘空间不足",
                    content=f"磁盘剩余空间 {free_pct:.1f}%（{usage.free // (1024**3)} GB），请及时清理。",
                    priority="high",
                )
                session.add(notif)
                session.commit()
        finally:
            engine.dispose()
        logger.warning("disk_space_low", free_pct=round(free_pct, 1), free_gb=usage.free // (1024**3))
    else:
        logger.info("disk_space_ok", free_pct=round(free_pct, 1))

STALE_THRESHOLD_MINUTES = 60


@celery_app.task(name="app.system.tasks.consistency_scan")
def consistency_scan():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    runtime_cfg = get_sync_runtime_config()
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    try:
        with Session(engine) as session:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)

            # Find stale processing documents (stuck > 1hr)
            stale_docs = session.execute(
                select(Document.id).where(
                    Document.status == DocumentStatus.PROCESSING,
                    Document.updated_at < cutoff,
                )
            ).scalars().all()

            if stale_docs:
                session.execute(
                    update(Document)
                    .where(Document.id.in_(stale_docs))
                    .values(status=DocumentStatus.ERROR, error_message="Processing timed out (stuck > 1hr)")
                )
                logger.warning("consistency_scan_stale_docs", count=len(stale_docs))

            # Find stale deleting KBs (stuck > 1hr)
            stale_kbs = session.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.status == KBStatus.DELETING,
                    KnowledgeBase.updated_at < cutoff,
                )
            ).scalars().all()

            if stale_kbs:
                from app.knowledge.ingestion.tasks import cascade_delete_kb
                for kb_id in stale_kbs:
                    cascade_delete_kb.delay(str(kb_id))
                logger.warning("consistency_scan_stale_kbs", count=len(stale_kbs))

            # E8: Cross-storage consistency — orphan Milvus collections
            orphan_collections = 0
            try:
                from app.knowledge.milvus.service import MilvusService
                milvus_svc = MilvusService(runtime_cfg=runtime_cfg)
                from pymilvus import utility
                existing_collections = utility.list_collections()
                active_kb_ids = session.execute(
                    select(KnowledgeBase.id).where(KnowledgeBase.status != KBStatus.DELETING)
                ).scalars().all()
                active_names = {f"kb_{kid}" for kid in active_kb_ids}
                for coll_name in existing_collections:
                    if coll_name.startswith("kb_") and coll_name not in active_names:
                        try:
                            milvus_svc.drop_collection(coll_name)
                            orphan_collections += 1
                        except Exception:
                            pass
            except Exception:
                logger.debug("consistency_scan_milvus_skip", reason="milvus unavailable")

            # PG-Milvus vector consistency: verify vector_id references are valid
            orphan_vectors = 0
            try:
                from app.knowledge.models import Chunk
                chunks_with_vectors = session.execute(
                    select(Chunk.id, Chunk.vector_id, Chunk.knowledge_base_id).where(
                        Chunk.vector_id.isnot(None)
                    )
                ).all()

                # Group by KB for batch verification
                kb_vectors: dict[str, list[tuple]] = {}
                for chunk_id, vector_id, kb_id in chunks_with_vectors:
                    kb_key = str(kb_id)
                    kb_vectors.setdefault(kb_key, []).append((chunk_id, vector_id))

                for kb_id_str, chunk_pairs in kb_vectors.items():
                    collection_name = f"kb_{kb_id_str}"
                    try:
                        vector_ids_to_check = [vp[1] for vp in chunk_pairs]
                        existing = milvus_svc._client.get(
                            collection_name=collection_name,
                            ids=vector_ids_to_check,
                            output_fields=["id"],
                        )
                        existing_ids = {r["id"] for r in existing}
                        for chunk_id, vector_id in chunk_pairs:
                            if vector_id not in existing_ids:
                                session.execute(
                                    update(Chunk)
                                    .where(Chunk.id == chunk_id)
                                    .values(vector_id=None)
                                )
                                orphan_vectors += 1
                    except Exception:
                        pass  # collection may not exist, skip
                if orphan_vectors:
                    logger.warning("consistency_scan_orphan_vectors", count=orphan_vectors)
            except Exception:
                logger.debug("consistency_scan_vector_check_skip", reason="error during vector check")

            # E8: PG-MinIO file consistency — docs whose file_path is missing in bucket
            missing_files: list[tuple[str, str, str]] = []  # (doc_id, title, creator_id)
            try:
                import asyncio as _asyncio

                from app.knowledge.storage.minio_service import MinIOService
                minio_svc = MinIOService(runtime_cfg)
                active_docs = session.execute(
                    select(Document.id, Document.title, Document.file_path, Document.created_by)
                    .where(
                        Document.file_path.isnot(None),
                        Document.status == DocumentStatus.COMPLETED,
                        Document.is_archived.is_(False),
                    )
                ).all()

                async def _probe(paths: list[str]) -> set[str]:
                    found: set[str] = set()
                    for p in paths:
                        try:
                            # head_object equivalent via boto3 client
                            await _asyncio.to_thread(
                                minio_svc.client.head_object, Bucket=minio_svc.bucket, Key=p
                            )
                            found.add(p)
                        except Exception:
                            pass
                    return found

                paths = [d.file_path for d in active_docs]
                found_paths = _asyncio.run(_probe(paths)) if paths else set()

                for d in active_docs:
                    if d.file_path not in found_paths:
                        missing_files.append((str(d.id), d.title, str(d.created_by)))

                if missing_files:
                    session.execute(
                        update(Document)
                        .where(Document.id.in_([uuid.UUID(mf[0]) for mf in missing_files]))
                        .values(status=DocumentStatus.ERROR, error_message="File missing in object storage")
                    )
                    logger.warning("consistency_scan_missing_files", count=len(missing_files))
            except Exception:
                logger.debug("consistency_scan_minio_skip", exc_info=True)

            # S-M10: Notify creators + admins when inconsistencies detected
            try:
                from app.auth.models import User, UserRole
                from app.system.models import Notification

                notify_creators: dict[str, list[str]] = {}
                for doc_id in stale_docs:
                    doc = session.get(Document, doc_id)
                    if doc and doc.created_by:
                        notify_creators.setdefault(str(doc.created_by), []).append(f"文档处理超时: {doc.title}")
                for doc_id, title, creator in missing_files:
                    notify_creators.setdefault(creator, []).append(f"文档文件丢失: {title}")

                for user_id, msgs in notify_creators.items():
                    session.add(Notification(
                        user_id=uuid.UUID(user_id),
                        type="consistency_issue",
                        title="一致性扫描发现问题",
                        content="\n".join(msgs[:10]),
                        priority="high",
                    ))

                total_issues = (
                    len(stale_docs) + len(stale_kbs) + orphan_collections
                    + orphan_vectors + len(missing_files)
                )
                if total_issues > 0:
                    admin_ids = session.execute(
                        select(User.id).where(
                            User.role == UserRole.SYSTEM_ADMIN, User.is_active.is_(True)
                        )
                    ).scalars().all()
                    summary = (
                        f"卡任务: {len(stale_docs)} 文档 / {len(stale_kbs)} KB | "
                        f"孤儿: {orphan_collections} collection / {orphan_vectors} 向量 / "
                        f"{len(missing_files)} 文件丢失"
                    )
                    for admin_id in admin_ids:
                        session.add(Notification(
                            user_id=admin_id,
                            type="consistency_scan",
                            title="一致性扫描异常汇总",
                            content=summary,
                            priority="normal",
                        ))
            except Exception:
                logger.debug("consistency_scan_notify_skip", exc_info=True)

            session.commit()
            logger.info(
                "consistency_scan_complete",
                stale_docs=len(stale_docs),
                stale_kbs=len(stale_kbs),
                orphan_collections=orphan_collections,
                orphan_vectors=orphan_vectors,
                missing_files=len(missing_files),
            )
    finally:
        engine.dispose()
