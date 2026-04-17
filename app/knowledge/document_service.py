import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, QuotaExceededError, ValidationError
from app.knowledge.ingestion.parser import (
    compute_file_hash,
    detect_source_type,
    sanitize_filename,
)
from app.knowledge.models import Document, DocumentStatus
from app.knowledge.storage.minio_service import MinIOService
from app.system.models import SystemSettings

logger = structlog.get_logger(__name__)

MAX_DOCS_PER_KB = 500
MAX_STORAGE_PER_KB_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


class DocumentService:
    def __init__(self, db: AsyncSession, minio: MinIOService | None = None):
        self.db = db
        self.minio = minio or MinIOService()

    async def upload_document(
        self,
        kb_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        filename: str,
        file_data: bytes,
        user_id: uuid.UUID,
    ) -> Document:
        await self.check_doc_quota(kb_id)
        await self.check_storage_quota(kb_id, len(file_data))

        safe_name = sanitize_filename(filename)
        source_type = detect_source_type(safe_name)
        file_hash = compute_file_hash(file_data)

        # Dedup check within same KB
        existing = await self.db.scalar(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.file_hash == file_hash,
                Document.is_archived.is_(False),
            )
        )
        if existing is not None:
            raise ConflictError(f"Duplicate file detected (matches document '{existing.title}')")

        # Content validation deferred to Celery task (parse is expensive, don't block upload)

        # Upload to MinIO
        key = f"kb/{kb_id}/{uuid.uuid4()}/{safe_name}"
        await self.minio.upload(key, file_data)

        doc = Document(
            knowledge_base_id=kb_id,
            folder_id=folder_id,
            title=safe_name,
            source_type=source_type,
            file_path=key,
            file_size=len(file_data),
            file_hash=file_hash,
            status=DocumentStatus.PENDING,
            created_by=user_id,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        logger.info("document_uploaded", doc_id=str(doc.id), kb_id=str(kb_id), title=safe_name)
        return doc

    async def get_document(self, doc_id: uuid.UUID) -> Document:
        doc = await self.db.get(Document, doc_id)
        if doc is None:
            raise NotFoundError("Document", str(doc_id))
        return doc

    async def list_documents(
        self,
        kb_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Document], int]:
        base = select(Document).where(
            Document.knowledge_base_id == kb_id,
            Document.is_archived.is_(False),
        )
        if folder_id is not None:
            base = base.where(Document.folder_id == folder_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            base.order_by(Document.position, Document.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def update_status(
        self,
        doc_id: uuid.UUID,
        status: DocumentStatus,
        error_message: str | None = None,
        chunk_count: int | None = None,
        token_count: int | None = None,
    ) -> None:
        values: dict = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if token_count is not None:
            values["token_count"] = token_count
        if status == DocumentStatus.COMPLETED:
            values["processed_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(Document).where(Document.id == doc_id).values(**values)
        )

    async def check_doc_quota(self, kb_id: uuid.UUID) -> None:
        limit = MAX_DOCS_PER_KB
        ss = await self.db.get(SystemSettings, 1)
        if ss and ss.settings:
            limit = ss.settings.get("quotas", {}).get("max_docs_per_kb", MAX_DOCS_PER_KB)

        count = (await self.db.execute(
            select(func.count()).where(
                Document.knowledge_base_id == kb_id,
                Document.is_archived.is_(False),
            )
        )).scalar() or 0
        if count >= limit:
            raise QuotaExceededError(f"Document quota exceeded (max {limit} per knowledge base)")

    async def check_storage_quota(self, kb_id: uuid.UUID, new_size: int) -> None:
        limit = MAX_STORAGE_PER_KB_BYTES
        ss = await self.db.get(SystemSettings, 1)
        if ss and ss.settings:
            limit = ss.settings.get("quotas", {}).get("max_storage_per_kb_bytes", MAX_STORAGE_PER_KB_BYTES)

        used = (await self.db.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.knowledge_base_id == kb_id,
                Document.is_archived.is_(False),
            )
        )).scalar() or 0
        if used + new_size > limit:
            raise QuotaExceededError(
                f"Storage quota exceeded "
                f"(used {used / (1024 ** 3):.2f} GB, limit {limit / (1024 ** 3):.2f} GB)"
            )
