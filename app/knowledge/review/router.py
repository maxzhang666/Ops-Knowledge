"""Review API (Plan 29 M3 + Plan 39 M2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.knowledge.models import Document, KnowledgeBase
from app.knowledge.review.reviewers import (
    is_user_reviewer_for_kb,
    kb_ids_user_can_review,
)
from app.knowledge.review.service import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    ReviewError,
    ReviewService,
)

router = APIRouter(tags=["review"])

# 多态 unit_type 白名单
ALLOWED_UNIT_TYPES = {"document", "entry"}


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


# ── Plan 39 M2 — 全局审核中心 endpoints ────────────────────────────────


class ReviewItemView(BaseModel):
    """跨 KB 待审 unit 视图。多 source_type 时 unit_type 区分类型。"""
    unit_type: str
    unit_id: uuid.UUID
    kb_id: uuid.UUID
    kb_name: str
    title: str
    # 文件型独占：file source_type（pdf/markdown/...）让前端选预览方式
    # 条目型 None；前端按 unit_type 路由到 markdown 渲染
    file_source_type: str | None = None
    chunk_count: int
    review_status: str
    review_comment: str | None
    submitted_by: uuid.UUID
    submitted_at: datetime
    reviewer_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None


class PendingCountResponse(BaseModel):
    count: int


@router.get("/review/pending/count", response_model=PendingCountResponse)
async def review_pending_count(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PendingCountResponse:
    """顶部徽章用：当前用户可审的 pending unit 总数。"""
    kb_ids = await kb_ids_user_can_review(db, current_user)
    if kb_ids is not None and not kb_ids:
        return PendingCountResponse(count=0)
    base = select(func.count(Document.id)).where(
        Document.review_status == REVIEW_PENDING,
        Document.is_archived.is_(False),
        Document.created_by != current_user.id,  # 不算自己提交的
    )
    if kb_ids is not None:
        base = base.where(Document.knowledge_base_id.in_(kb_ids))
    n = (await db.execute(base)).scalar() or 0
    return PendingCountResponse(count=int(n))


@router.get("/review/pending", response_model=PaginatedResponse)
async def review_pending_list(
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    kb_id: uuid.UUID | None = Query(None, description="按 KB 过滤"),
    unit_type: str | None = Query(None, description="按 unit_type 过滤（document/entry/...）"),
    db: AsyncSession = Depends(get_db),
):
    """跨 KB 待审 units 列表，分页。仅返回当前用户可审的 KB。"""
    if unit_type and unit_type not in ALLOWED_UNIT_TYPES:
        raise HTTPException(400, f"unit_type must be one of {ALLOWED_UNIT_TYPES}")
    accessible_kb_ids = await kb_ids_user_can_review(db, current_user)
    if accessible_kb_ids is not None and not accessible_kb_ids:
        return PaginatedResponse(
            items=[], total=0,
            page=pagination.page, page_size=pagination.page_size,
        )
    if kb_id is not None:
        if accessible_kb_ids is not None and kb_id not in accessible_kb_ids:
            raise HTTPException(403, "No review access to this KB")
        accessible_kb_ids = [kb_id]
    # 当前 unit_type 仅 document（Plan 41 加 entry 后扩展）
    items, total = await _query_pending_documents(
        db, accessible_kb_ids, current_user.id,
        offset=pagination.offset, limit=pagination.page_size,
    )
    return PaginatedResponse(
        items=[i.model_dump() for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


async def _query_pending_documents(
    db: AsyncSession,
    accessible_kb_ids: list[uuid.UUID] | None,
    current_user_id: uuid.UUID,
    offset: int,
    limit: int,
) -> tuple[list[ReviewItemView], int]:
    """document 维度的待审查询。Plan 41 加 entries 时新增 _query_pending_entries 并合并。"""
    base = (
        select(Document, KnowledgeBase.name)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            Document.review_status == REVIEW_PENDING,
            Document.is_archived.is_(False),
            Document.created_by != current_user_id,
        )
    )
    if accessible_kb_ids is not None:
        base = base.where(Document.knowledge_base_id.in_(accessible_kb_ids))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await db.execute(count_stmt)).scalar() or 0)

    rows = (await db.execute(
        base.order_by(Document.last_pending_started_at.asc().nulls_last(), Document.created_at.asc())
        .offset(offset).limit(limit)
    )).all()
    items: list[ReviewItemView] = []
    for doc, kb_name in rows:
        items.append(ReviewItemView(
            unit_type="document",
            unit_id=doc.id,
            kb_id=doc.knowledge_base_id,
            kb_name=kb_name,
            title=doc.title,
            file_source_type=doc.source_type,
            chunk_count=doc.chunk_count,
            review_status=doc.review_status or "",
            review_comment=doc.review_comment,
            submitted_by=doc.created_by,
            submitted_at=doc.last_pending_started_at or doc.created_at,
            reviewer_id=doc.reviewer_id,
            reviewed_at=doc.reviewed_at,
        ))
    return items, total


@router.get("/review/history", response_model=PaginatedResponse)
async def review_history(
    current_user: CurrentUser,
    mode: str = Query("reviewed_by_me", pattern="^(reviewed_by_me|submitted_by_me)$"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """审核历史。mode：reviewed_by_me（我审过）/ submitted_by_me（我提交的）"""
    # reviewed_by_me 仅看已决（approved/rejected）；submitted_by_me 包括
    # pending（作者要能跟踪自己的提交进度）
    base = (
        select(Document, KnowledgeBase.name)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
    )
    if mode == "reviewed_by_me":
        base = base.where(
            Document.review_status.in_([REVIEW_APPROVED, REVIEW_REJECTED]),
            Document.reviewer_id == current_user.id,
        )
    else:  # submitted_by_me
        base = base.where(
            Document.review_status.in_([REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED]),
            Document.created_by == current_user.id,
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await db.execute(count_stmt)).scalar() or 0)

    rows = (await db.execute(
        base.order_by(Document.reviewed_at.desc().nulls_last())
        .offset(pagination.offset).limit(pagination.page_size)
    )).all()
    items: list[ReviewItemView] = []
    for doc, kb_name in rows:
        items.append(ReviewItemView(
            unit_type="document",
            unit_id=doc.id,
            kb_id=doc.knowledge_base_id,
            kb_name=kb_name,
            title=doc.title,
            file_source_type=doc.source_type,
            chunk_count=doc.chunk_count,
            review_status=doc.review_status or "",
            review_comment=doc.review_comment,
            submitted_by=doc.created_by,
            submitted_at=doc.last_pending_started_at or doc.created_at,
            reviewer_id=doc.reviewer_id,
            reviewed_at=doc.reviewed_at,
        ))
    return PaginatedResponse(
        items=[i.model_dump() for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# ── 多态审核 endpoints — Plan 39 spec §14.7 ──────────────────────────


@router.post(
    "/review/{unit_type}/{unit_id}/approve",
    response_model=ReviewDecisionResponse,
)
async def approve_unit(
    unit_type: str,
    unit_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return await _decide_unit(unit_type, unit_id, body, current_user, db, action="approve")


@router.post(
    "/review/{unit_type}/{unit_id}/reject",
    response_model=ReviewDecisionResponse,
)
async def reject_unit(
    unit_type: str,
    unit_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if not body.comment or not body.comment.strip():
        raise HTTPException(400, "驳回必须填写理由（comment）")
    return await _decide_unit(unit_type, unit_id, body, current_user, db, action="reject")


@router.post(
    "/review/{unit_type}/{unit_id}/comment",
    response_model=ReviewDecisionResponse,
)
async def comment_unit(
    unit_type: str,
    unit_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """评论但不改变状态（用于"建议作者修改但不一票否决"的轻量反馈）。"""
    if not body.comment or not body.comment.strip():
        raise HTTPException(400, "评论内容不能为空")
    if unit_type not in ALLOWED_UNIT_TYPES:
        raise HTTPException(400, f"unit_type must be one of {ALLOWED_UNIT_TYPES}")
    doc = await db.get(Document, unit_id)
    if doc is None:
        raise HTTPException(404, "Unit not found")
    kb = await db.get(KnowledgeBase, doc.knowledge_base_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    if not await is_user_reviewer_for_kb(db, current_user, kb):
        raise HTTPException(403, "No review permission for this KB")
    if doc.created_by == current_user.id:
        raise HTTPException(403, "不能评论自己的提交")
    svc = ReviewService(db)
    try:
        updated = await svc.add_comment(unit_id, current_user.id, body.comment)
    except ReviewError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return ReviewDecisionResponse(
        document_id=updated.id,
        review_status=updated.review_status or "",
        reviewer_id=updated.reviewer_id,
        reviewed_at=updated.reviewed_at,
        review_comment=updated.review_comment,
    )


@router.post("/review/{unit_type}/{unit_id}/revert", response_model=ReviewDecisionResponse)
async def revert_unit_review(
    unit_type: str,
    unit_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """撤销审核（仅作者本人 / system_admin），把 review 状态重置回 pending。"""
    if unit_type not in ALLOWED_UNIT_TYPES:
        raise HTTPException(400, f"unit_type must be one of {ALLOWED_UNIT_TYPES}")
    doc = await db.get(Document, unit_id)
    if doc is None:
        raise HTTPException(404, "Unit not found")
    from app.auth.models import UserRole
    if doc.created_by != current_user.id and current_user.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(403, "仅作者本人或 system_admin 可撤销审核")
    svc = ReviewService(db)
    try:
        updated = await svc.request_re_review(unit_id)
    except ReviewError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return ReviewDecisionResponse(
        document_id=updated.id,
        review_status=updated.review_status or "",
        reviewer_id=updated.reviewer_id,
        reviewed_at=updated.reviewed_at,
        review_comment=updated.review_comment,
    )


async def _decide_unit(
    unit_type: str,
    unit_id: uuid.UUID,
    body: ReviewDecisionRequest,
    current_user,
    db: AsyncSession,
    *,
    action: str,
) -> ReviewDecisionResponse:
    """多态 unit 审核决策。当前仅 document 实现；Plan 41 加 entry 时扩展。"""
    if unit_type not in ALLOWED_UNIT_TYPES:
        raise HTTPException(400, f"unit_type must be one of {ALLOWED_UNIT_TYPES}")
    doc = await db.get(Document, unit_id)
    if doc is None:
        raise HTTPException(404, "Unit not found")
    kb = await db.get(KnowledgeBase, doc.knowledge_base_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    # 权限：必须是该 KB 的候选审核员（dept_admin / system_admin）
    if not await is_user_reviewer_for_kb(db, current_user, kb):
        raise HTTPException(403, "No review permission for this KB")
    if doc.created_by == current_user.id:
        raise HTTPException(403, "不能审批自己上传的文档")
    svc = ReviewService(db)
    try:
        if action == "approve":
            updated = await svc.approve(unit_id, current_user.id, body.comment)
        else:
            updated = await svc.reject(unit_id, current_user.id, body.comment)
    except ReviewError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return ReviewDecisionResponse(
        document_id=updated.id,
        review_status=updated.review_status or "",
        reviewer_id=updated.reviewer_id,
        reviewed_at=updated.reviewed_at,
        review_comment=updated.review_comment,
    )
