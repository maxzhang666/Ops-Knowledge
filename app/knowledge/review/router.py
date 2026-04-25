"""Review API (Plan 29 M3)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.knowledge.models import Document, KnowledgeBase
from app.knowledge.review.service import ReviewError, ReviewService

router = APIRouter(tags=["review"])


# ── Schemas ───────────────────────────────────────────────────────


class ReviewQueueItem(BaseModel):
    document_id: uuid.UUID
    title: str
    created_by: uuid.UUID
    created_at: datetime
    chunk_count: int


class ReviewQueueResponse(BaseModel):
    kb_id: uuid.UUID
    items: list[ReviewQueueItem]


class ReviewDecisionRequest(BaseModel):
    comment: str | None = Field(None, max_length=2000)


class ReviewDecisionResponse(BaseModel):
    document_id: uuid.UUID
    review_status: str
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_comment: str | None


# ── Routes ────────────────────────────────────────────────────────


@router.get("/knowledge/{kb_id}/review/queue", response_model=ReviewQueueResponse)
async def review_queue(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    # Reviewer 至少需要 edit 权限（owner / dept_admin / explicitly granted）。
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, required_level="edit",
    )
    docs = await ReviewService(db).list_pending(kb_id)
    return ReviewQueueResponse(
        kb_id=kb_id,
        items=[
            ReviewQueueItem(
                document_id=d.id,
                title=d.title,
                created_by=d.created_by,
                created_at=d.created_at,
                chunk_count=d.chunk_count,
            )
            for d in docs
        ],
    )


@router.post(
    "/knowledge/{kb_id}/documents/{doc_id}/review/approve",
    response_model=ReviewDecisionResponse,
)
async def approve_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return await _decide(kb_id, doc_id, body, current_user, db, action="approve")


@router.post(
    "/knowledge/{kb_id}/documents/{doc_id}/review/reject",
    response_model=ReviewDecisionResponse,
)
async def reject_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return await _decide(kb_id, doc_id, body, current_user, db, action="reject")


async def _decide(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user,
    db: AsyncSession,
    *,
    action: str,
) -> ReviewDecisionResponse:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, required_level="edit",
    )
    doc = await db.get(Document, doc_id)
    if doc is None or doc.knowledge_base_id != kb_id:
        raise HTTPException(404, "Document not found")
    # 业务约束：reviewer 不能审批自己上传的文档（防自审）
    if doc.created_by == current_user.id:
        raise HTTPException(403, "不能审批自己上传的文档，请请其他 reviewer 处理")
    svc = ReviewService(db)
    try:
        if action == "approve":
            updated = await svc.approve(doc_id, current_user.id, body.comment)
        else:
            updated = await svc.reject(doc_id, current_user.id, body.comment)
    except ReviewError as e:
        raise HTTPException(400, str(e))
    return ReviewDecisionResponse(
        document_id=updated.id,
        review_status=updated.review_status or "",
        reviewer_id=updated.reviewer_id,
        reviewed_at=updated.reviewed_at,
        review_comment=updated.review_comment,
    )
