"""Spec 25 §6 — 字典治理 endpoints。

挂在 /api/v1/knowledge/{kb_id}/tag-dictionary 下：
- GET     /                    list + 分页 + search
- POST    /                    create
- POST    /{id}/aliases        set_aliases
- POST    /{id}/rename         rename + 触发异步回填
- POST    /merge               merge N→1 + 触发异步回填
- POST    /{id}/delete         soft delete
- GET     /audit                操作历史

权限：KB owner 或 system_admin。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse
from app.knowledge.service import KBService
from app.knowledge.tagging.service import TagDictionaryService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/knowledge/{kb_id}/tag-dictionary",
    tags=["tag-dictionary"],
)


# ── Schemas ──────────────────────────────────────────────────────


class TagDictItem(BaseModel):
    id: uuid.UUID
    canonical: str
    aliases: list[str]
    usage_count: int
    is_deprecated: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagDictAuditItem(BaseModel):
    id: uuid.UUID
    dict_id: uuid.UUID | None
    op: str
    before: dict | None
    after: dict | None
    affected_entries: int | None
    actor_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateBody(BaseModel):
    canonical: str = Field(..., min_length=1, max_length=64)
    aliases: list[str] | None = None


class SetAliasesBody(BaseModel):
    aliases: list[str]


class RenameBody(BaseModel):
    canonical: str = Field(..., min_length=1, max_length=64)


class MergeBody(BaseModel):
    source_ids: list[uuid.UUID] = Field(..., min_length=1)
    target_id: uuid.UUID


# ── Endpoints ────────────────────────────────────────────────────


async def _require_kb_access(
    kb_id: uuid.UUID, current_user, db: AsyncSession, *, level: str = "edit",
):
    """权限：KB owner 或 system_admin 才能操作字典。"""
    kb = await KBService(db).get_kb(kb_id)
    await check_resource_access(
        current_user, "knowledge_base", kb.id, db, kb.created_by, level,
    )
    return kb


@router.get("", response_model=PaginatedResponse)
async def list_tags(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    search: str | None = Query(None, max_length=64),
    include_deprecated: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    await _require_kb_access(kb_id, current_user, db, level="view")
    svc = TagDictionaryService(db)
    items, total = await svc.list(
        kb_id, search=search, include_deprecated=include_deprecated,
        page=page, page_size=page_size,
    )
    return PaginatedResponse(
        items=[TagDictItem.model_validate(r).model_dump(mode="json") for r in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=TagDictItem, status_code=status.HTTP_201_CREATED)
async def create_tag(
    kb_id: uuid.UUID,
    body: CreateBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_kb_access(kb_id, current_user, db)
    svc = TagDictionaryService(db)
    row = await svc.create(kb_id, body.canonical, body.aliases, current_user.id)
    await db.commit()
    return TagDictItem.model_validate(row)


@router.post("/{dict_id}/aliases", response_model=TagDictItem)
async def set_aliases(
    kb_id: uuid.UUID,
    dict_id: uuid.UUID,
    body: SetAliasesBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_kb_access(kb_id, current_user, db)
    svc = TagDictionaryService(db)
    try:
        row = await svc.set_aliases(dict_id, body.aliases, current_user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if row.kb_id != kb_id:
        raise HTTPException(403, "Dictionary entry does not belong to this KB")
    await db.commit()
    return TagDictItem.model_validate(row)


@router.post("/{dict_id}/rename", response_model=TagDictItem)
async def rename_tag(
    kb_id: uuid.UUID,
    dict_id: uuid.UUID,
    body: RenameBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """改名 = 旧名进 aliases + 新名生效 + 异步回填 entries.tags / chunks.chunk_tags。"""
    from app.core.tasks import safe_delay
    from app.knowledge.tagging.tasks import backfill_tag_rename

    await _require_kb_access(kb_id, current_user, db)
    svc = TagDictionaryService(db)
    try:
        row, old_canonical = await svc.rename(dict_id, body.canonical, current_user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if row.kb_id != kb_id:
        raise HTTPException(403, "Dictionary entry does not belong to this KB")
    await db.commit()
    if old_canonical != row.canonical:
        safe_delay(
            backfill_tag_rename,
            str(kb_id), old_canonical, row.canonical,
        )
        logger.info(
            "tag_dict.rename.backfill_enqueued",
            kb_id=str(kb_id),
            old=old_canonical, new=row.canonical,
            actor=str(current_user.id),
        )
    return TagDictItem.model_validate(row)


@router.post("/merge", response_model=TagDictItem)
async def merge_tags(
    kb_id: uuid.UUID,
    body: MergeBody,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """合并多个 canonical 到 target，sources 软删除 + 异步回填。"""
    from app.core.tasks import safe_delay
    from app.knowledge.tagging.tasks import backfill_tag_merge

    await _require_kb_access(kb_id, current_user, db)
    if body.target_id in body.source_ids:
        raise HTTPException(400, "target_id cannot appear in source_ids")
    svc = TagDictionaryService(db)
    try:
        target, source_canonicals = await svc.merge(
            body.source_ids, body.target_id, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if target.kb_id != kb_id:
        raise HTTPException(403, "Target does not belong to this KB")
    await db.commit()
    if source_canonicals:
        safe_delay(
            backfill_tag_merge,
            str(kb_id), source_canonicals, target.canonical,
        )
        logger.info(
            "tag_dict.merge.backfill_enqueued",
            kb_id=str(kb_id), sources=source_canonicals,
            target=target.canonical, actor=str(current_user.id),
        )
    return TagDictItem.model_validate(target)


@router.post("/{dict_id}/delete", response_model=TagDictItem)
async def soft_delete_tag(
    kb_id: uuid.UUID,
    dict_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """软删除（is_deprecated=true）。历史 entries.tags 保留，仅停止字典命中。"""
    await _require_kb_access(kb_id, current_user, db)
    svc = TagDictionaryService(db)
    try:
        row = await svc.soft_delete(dict_id, current_user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if row.kb_id != kb_id:
        raise HTTPException(403, "Dictionary entry does not belong to this KB")
    await db.commit()
    return TagDictItem.model_validate(row)


@router.get("/audit", response_model=PaginatedResponse)
async def list_audit(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    await _require_kb_access(kb_id, current_user, db, level="view")
    svc = TagDictionaryService(db)
    items, total = await svc.list_audit(kb_id, page, page_size)
    return PaginatedResponse(
        items=[TagDictAuditItem.model_validate(r).model_dump(mode="json") for r in items],
        total=total, page=page, page_size=page_size,
    )
