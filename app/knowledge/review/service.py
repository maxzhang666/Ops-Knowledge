"""ReviewService — Knowledge review workflow (Plan 29 M2).

State machine on ``Document.review_status``:

    None (KB.review_required=False, legacy)
        ↓ KB toggled on, doc COMPLETED
    pending  ── approve ──→ approved   (visible in retrieval)
        └──── reject ───→ rejected   (excluded from retrieval)

每次状态翻转通知 created_by + 候选 reviewer 集合（KB owner + dept_admin）。
检索路径在 KB.review_required=True 时仅放行 review_status=approved。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.knowledge.models import Chunk, Document, KnowledgeBase
from app.system.models import Notification

logger = structlog.get_logger(__name__)


REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_STATES = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)


class ReviewError(ValueError):
    pass


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 写入路径 ──────────────────────────────────────────────────

    async def submit_for_review(self, doc_id: uuid.UUID) -> Document:
        """ingestion 完成 COMPLETED 时调用。仅在 KB.review_required=True
        且当前 review_status 为空/None 时才标 pending；否则保持原状（已审过的
        重新跑 reprocess 不应被打回 pending —— 那由专门的 ``request_re_review``
        管理）。
        """
        doc = await self._get_doc(doc_id)
        kb = await self.db.get(KnowledgeBase, doc.knowledge_base_id)
        if kb is None or not kb.review_required:
            return doc
        if doc.review_status is not None:
            return doc
        doc.review_status = REVIEW_PENDING
        doc.reviewer_id = None
        doc.reviewed_at = None
        doc.review_comment = None
        doc.last_pending_started_at = datetime.now(timezone.utc)
        await self._set_chunks_excluded(doc_id, True)
        await self.db.flush()
        await self._notify_reviewers(kb, doc)
        return doc

    async def approve(
        self,
        doc_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        comment: str | None = None,
    ) -> Document:
        return await self._decide(doc_id, reviewer_id, REVIEW_APPROVED, comment)

    async def reject(
        self,
        doc_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        comment: str | None = None,
    ) -> Document:
        return await self._decide(doc_id, reviewer_id, REVIEW_REJECTED, comment)

    async def add_comment(
        self,
        doc_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        comment: str,
    ) -> Document:
        """Plan 39 §14.5 — 评论但不变状态：用于"建议作者修改但不一票否决"
        的轻量反馈。覆盖 review_comment 并通知作者。"""
        doc = await self._get_doc(doc_id)
        doc.review_comment = comment
        await self.db.flush()
        # 通知作者：有审核员留言
        from app.system.models import Notification
        self.db.add(Notification(
            user_id=doc.created_by,
            type="review_comment",
            title=f"文档「{doc.title}」收到审核反馈",
            content=comment,
            priority="normal",
            resource_type="document",
            resource_id=doc.id,
        ))
        await self.db.flush()
        logger.info(
            "review_comment_added",
            doc_id=str(doc_id), reviewer=str(reviewer_id),
        )
        return doc

    async def request_re_review(self, doc_id: uuid.UUID) -> Document:
        """运维路径：内容大改后强制再审。"""
        doc = await self._get_doc(doc_id)
        kb = await self.db.get(KnowledgeBase, doc.knowledge_base_id)
        if kb is None or not kb.review_required:
            return doc
        doc.review_status = REVIEW_PENDING
        doc.reviewer_id = None
        doc.reviewed_at = None
        doc.review_comment = None
        doc.last_pending_started_at = datetime.now(timezone.utc)
        await self._set_chunks_excluded(doc_id, True)
        await self.db.flush()
        await self._notify_reviewers(kb, doc)
        return doc

    # ── 读取路径 ──────────────────────────────────────────────────

    async def list_pending(
        self, kb_id: uuid.UUID, *, limit: int = 50,
    ) -> list[Document]:
        rows = (await self.db.execute(
            select(Document)
            .where(
                Document.knowledge_base_id == kb_id,
                Document.review_status == REVIEW_PENDING,
                Document.is_archived.is_(False),
            )
            .order_by(Document.created_at.asc())
            .limit(limit)
        )).scalars().all()
        return list(rows)

    # ── 内部 ──────────────────────────────────────────────────────

    async def _decide(
        self,
        doc_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        new_status: str,
        comment: str | None,
    ) -> Document:
        if new_status not in (REVIEW_APPROVED, REVIEW_REJECTED):
            raise ReviewError(f"Unsupported decision: {new_status}")
        doc = await self._get_doc(doc_id)
        if doc.review_status not in (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED):
            raise ReviewError("Document is not subject to review")
        doc.review_status = new_status
        doc.reviewer_id = reviewer_id
        doc.reviewed_at = datetime.now(timezone.utc)
        doc.review_comment = comment
        # Plan 39 — chunks.review_excluded 跟随 review_status：
        # approved → false（进入召回）；rejected → 保持 true（永不召回）
        if new_status == REVIEW_APPROVED:
            await self._set_chunks_excluded(doc_id, False)
        await self.db.flush()
        await self._notify_owner_decision(doc, new_status, comment)
        logger.info(
            "review_decided",
            doc_id=str(doc_id), status=new_status, reviewer=str(reviewer_id),
        )
        return doc

    async def _set_chunks_excluded(
        self, doc_id: uuid.UUID, excluded: bool,
    ) -> None:
        """Plan 39 — 同步 chunks.review_excluded。
        Plan 40 M2 — 多态 unit FK 切读。
        审核期内容隔离派生列：pending/rejected unit 的 chunks 置 true，
        不参与召回 / 命中统计 / 治理动态分。"""
        await self.db.execute(
            update(Chunk)
            .where(Chunk.unit_type == "document", Chunk.unit_id == doc_id)
            .values(review_excluded=excluded)
        )

    async def _get_doc(self, doc_id: uuid.UUID) -> Document:
        doc = await self.db.get(Document, doc_id)
        if doc is None:
            raise NotFoundError("Document", str(doc_id))
        return doc

    async def _candidate_reviewers(
        self, kb: KnowledgeBase, *, exclude: set[uuid.UUID] | None = None,
    ) -> list[uuid.UUID]:
        """Plan 39 M2 — 候选审核员 spec 实现。
        delegate 到 reviewers.get_candidate_reviewers，
        覆盖 DepartmentResource (shared) + system_admin + KB owner dept fallback。
        """
        from app.knowledge.review.reviewers import get_candidate_reviewers
        return await get_candidate_reviewers(self.db, kb, exclude_user_ids=exclude)

    async def _notify_reviewers(self, kb: KnowledgeBase, doc: Document) -> None:
        # Plan 39 M2 — 去重：同一 unit 在 pending 期间多次提交仅发一条
        # review_pending；approved/rejected 后再次进入 pending 才重置（last_pending_started_at 推进）
        if doc.last_pending_started_at:
            existing = await self.db.execute(
                select(Notification.id).where(
                    Notification.type == "review_pending",
                    Notification.resource_id == doc.id,
                    Notification.created_at > doc.last_pending_started_at,
                ).limit(1)
            )
            if existing.first() is not None:
                logger.debug(
                    "review_pending_notification_deduped",
                    doc_id=str(doc.id),
                    last_pending_started_at=doc.last_pending_started_at.isoformat(),
                )
                return
        targets = await self._candidate_reviewers(kb, exclude={doc.created_by})
        if not targets:
            # 单人 KB —— owner 就是上传者；至少给个自我提醒
            targets = [doc.created_by]
        title = f"待审批：「{doc.title}」"
        content = f"知识库「{kb.name}」有新文档等待审批。"
        for uid in targets:
            self.db.add(Notification(
                user_id=uid,
                type="review_pending",
                title=title,
                content=content,
                priority="normal",
                resource_type="document",
                resource_id=doc.id,
            ))
        await self.db.flush()

    async def _notify_owner_decision(
        self, doc: Document, status: str, comment: str | None,
    ) -> None:
        verb = "已通过" if status == REVIEW_APPROVED else "已拒绝"
        title = f"文档「{doc.title}」审批{verb}"
        body = comment or ("文档已发布到知识库。" if status == REVIEW_APPROVED else "请按反馈调整后再次提交。")
        self.db.add(Notification(
            user_id=doc.created_by,
            type=f"review_{status}",
            title=title,
            content=body,
            priority="normal",
            resource_type="document",
            resource_id=doc.id,
        ))
        await self.db.flush()
