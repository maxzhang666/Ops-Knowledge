import uuid

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import apply_dept_scope
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.department.service import DepartmentService
from app.knowledge.models import KBStatus, KnowledgeBase
from app.knowledge.schemas import KBCreate, KBUpdate
from app.system.models import SystemSettings

logger = structlog.get_logger(__name__)

MAX_KB_PER_USER = 50


class KBService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_kb(self, data: KBCreate, user_id: uuid.UUID) -> KnowledgeBase:
        await self.check_kb_quota(user_id)

        # Plan 41 — 校验 source_type 已注册
        from app.knowledge.sources import is_supported as _src_supported
        if not _src_supported(data.source_type):
            raise ValueError(f"unsupported source_type: {data.source_type}")

        provider_id = data.embedding_provider_id
        model_name = data.embedding_model_name
        registry_id = data.embedding_model_id

        # Fallback chain for embedding config:
        #   1) explicit registry_id from payload → backfill provider/name from it
        #   2) no payload → use system default_embedding_model_id
        #   3) still nothing → leave NULL (KB shows "未配置", retrieval/upload blocked)
        from app.model.models import ModelRegistryEntry

        if not registry_id and not (provider_id and model_name):
            ss = await self.db.get(SystemSettings, 1)
            default_id = (ss.settings or {}).get("default_embedding_model_id") if ss else None
            if default_id:
                try:
                    registry_id = uuid.UUID(str(default_id))
                except (ValueError, TypeError):
                    registry_id = None

        if registry_id and (not provider_id or not model_name):
            entry = await self.db.get(ModelRegistryEntry, registry_id)
            if entry is not None:
                provider_id = provider_id or entry.provider_id
                model_name = model_name or entry.model_id

        kb = KnowledgeBase(
            name=data.name,
            description=data.description,
            source_type=data.source_type,
            embedding_provider_id=provider_id,
            embedding_model_name=model_name,
            embedding_model_id=registry_id,
            chunking_config=data.chunking_config,
            retrieval_config=data.retrieval_config,
            created_by=user_id,
        )
        self.db.add(kb)
        await self.db.flush()
        await self.db.refresh(kb)  # load server-generated created_at/updated_at/counts

        if data.share_to_dept:
            dept_svc = DepartmentService(self.db)
            dept_ids = await dept_svc.get_user_department_ids(user_id)
            for dept_id in dept_ids:
                await dept_svc.share_resource(dept_id, "knowledge_base", kb.id, "view", user_id)

        logger.info("kb_created", kb_id=str(kb.id), name=data.name)
        return kb

    async def get_kb(self, kb_id: uuid.UUID) -> KnowledgeBase:
        kb = await self.db.get(KnowledgeBase, kb_id)
        if kb is None or kb.status == KBStatus.DELETING:
            raise NotFoundError("KnowledgeBase", str(kb_id))
        return kb

    async def list_kbs(
        self, user_id: uuid.UUID, accessible_ids: list[uuid.UUID] | None, offset: int = 0, limit: int = 20
    ) -> tuple[list[KnowledgeBase], int]:
        base = select(KnowledgeBase).where(KnowledgeBase.status != KBStatus.DELETING)
        if accessible_ids is not None:
            stmt = apply_dept_scope(
                base, accessible_ids, user_id,
                KnowledgeBase.id, KnowledgeBase.created_by,
            )
        else:
            stmt = base

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            stmt.order_by(KnowledgeBase.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def update_kb(self, kb_id: uuid.UUID, data: KBUpdate, if_unmodified_since=None) -> KnowledgeBase:
        kb = await self.get_kb(kb_id)
        if if_unmodified_since and kb.updated_at != if_unmodified_since:
            raise ConflictError("Knowledge base has been modified by another user")
        updates = data.model_dump(exclude_unset=True)

        # When caller sets embedding_model_id (registry FK), backfill the
        # legacy embedding_provider_id / embedding_model_name fields from the
        # registry so the UI + old code paths continue to read a name.
        if "embedding_model_id" in updates and updates["embedding_model_id"]:
            from app.model.models import ModelRegistryEntry
            entry = await self.db.get(ModelRegistryEntry, updates["embedding_model_id"])
            if entry is not None:
                updates.setdefault("embedding_provider_id", entry.provider_id)
                updates.setdefault("embedding_model_name", entry.model_id)

        for k, v in updates.items():
            setattr(kb, k, v)
        await self.db.flush()
        await self.db.refresh(kb)  # load server-updated updated_at
        return kb

    async def mark_kb_deleting(self, kb_id: uuid.UUID) -> None:
        kb = await self.get_kb(kb_id)
        kb.status = KBStatus.DELETING
        await self.db.flush()

    async def increment_doc_count(self, kb_id: uuid.UUID, delta: int = 1) -> None:
        await self.db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(document_count=KnowledgeBase.document_count + delta)
        )

    async def update_chunk_count(self, kb_id: uuid.UUID, chunk_delta: int) -> None:
        await self.db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(chunk_count=KnowledgeBase.chunk_count + chunk_delta)
        )

    async def check_kb_quota(self, user_id: uuid.UUID) -> None:
        limit = MAX_KB_PER_USER
        ss = await self.db.get(SystemSettings, 1)
        if ss and ss.settings:
            limit = ss.settings.get("quotas", {}).get("max_kbs_per_user", MAX_KB_PER_USER)

        count = (await self.db.execute(
            select(func.count()).where(
                KnowledgeBase.created_by == user_id,
                KnowledgeBase.status != KBStatus.DELETING,
            )
        )).scalar() or 0
        if count >= limit:
            raise ValidationError(f"Knowledge base quota exceeded (max {limit})")
