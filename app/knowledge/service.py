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
        kb = KnowledgeBase(
            name=data.name,
            description=data.description,
            embedding_provider_id=data.embedding_provider_id,
            embedding_model_name=data.embedding_model_name,
            chunking_config=data.chunking_config,
            retrieval_config=data.retrieval_config,
            created_by=user_id,
        )
        self.db.add(kb)
        await self.db.flush()

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
        self, user_id: uuid.UUID, accessible_ids: list[uuid.UUID], offset: int = 0, limit: int = 20
    ) -> tuple[list[KnowledgeBase], int]:
        base = select(KnowledgeBase).where(KnowledgeBase.status != KBStatus.DELETING)
        stmt = apply_dept_scope(
            base, accessible_ids, user_id,
            KnowledgeBase.id, KnowledgeBase.created_by,
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            stmt.order_by(KnowledgeBase.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def update_kb(self, kb_id: uuid.UUID, data: KBUpdate) -> KnowledgeBase:
        kb = await self.get_kb(kb_id)
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(kb, k, v)
        await self.db.flush()
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
