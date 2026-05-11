"""Plan 41 — 条目型 KB 的 CRUD endpoints。

委托 EntrySourcePlugin 处理业务逻辑（create_unit / update_unit 等），
router 层仅负责 HTTP 协议 + 权限校验。
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.core.runtime_config import get_runtime_config
from app.knowledge.chunk_service import ChunkService
from app.knowledge.milvus.service import MilvusService, kb_collection_name
from app.knowledge.models import Chunk, KnowledgeBase, KnowledgeEntry
from app.knowledge.schemas import EntryCreate, EntryResponse, EntryUpdate
from app.knowledge.sources import get_plugin

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/knowledge/{kb_id}/entries", tags=["entries"])


async def _purge_milvus_for_entries(
    db: AsyncSession,
    kb_id: uuid.UUID,
    entry_ids: list[uuid.UUID],
) -> None:
    """Best-effort 清理 milvus 中 entry 对应的旧向量（编辑/删除时调）。

    不清理会导致：embedding 用 chunk.id 作为 milvus PK upsert，编辑后旧
    chunk_id 在 PG 已被删但 milvus 仍残留 → searcher 直接读 milvus entity.content
    返回老内容。

    Milvus collection schema 字段名留作 legacy 仍叫 'document_id'，但里面存
    的是 unit_id 值（与 file 路径完全对齐）。"""
    if not entry_ids:
        return
    try:
        cfg = await get_runtime_config(db)
        collection = kb_collection_name(kb_id)
        milvus = MilvusService(runtime_cfg=cfg)
        try:
            if milvus.collection_exists(collection):
                for eid in entry_ids:
                    milvus.delete_by_filter(
                        collection, f'document_id == "{eid}"',
                    )
        finally:
            milvus.close()
    except Exception:
        # best-effort —— 残留只是有"幽灵向量"，下次 reindex 可清；
        # 不能因为 milvus 不可用阻塞 PG 主路径
        logger.warning(
            "entry.milvus_purge_failed",
            kb_id=str(kb_id), count=len(entry_ids), exc_info=True,
        )


async def _build_entry_responses(
    db: AsyncSession,
    entries: list[KnowledgeEntry],
) -> list[EntryResponse]:
    """批量构建 EntryResponse —— 一次性查回 created_by / reviewer 的 username，
    避免 N+1。供 list/get/create/update 共用。"""
    if not entries:
        return []
    user_ids: set[uuid.UUID] = set()
    for e in entries:
        if e.created_by:
            user_ids.add(e.created_by)
        if e.reviewer_id:
            user_ids.add(e.reviewer_id)
    name_map: dict[uuid.UUID, str] = {}
    if user_ids:
        rows = (await db.execute(
            select(User.id, User.username).where(User.id.in_(user_ids))
        )).all()
        name_map = {uid: uname for uid, uname in rows}
    out: list[EntryResponse] = []
    for e in entries:
        resp = EntryResponse.model_validate(e)
        resp.created_by_name = name_map.get(e.created_by)
        resp.reviewer_name = name_map.get(e.reviewer_id) if e.reviewer_id else None
        out.append(resp)
    return out


@router.post("", response_model=EntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    kb_id: uuid.UUID,
    data: EntryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    if kb.source_type != "entry":
        raise HTTPException(400, "This KB is not entry-type")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    plugin = get_plugin("entry")
    payload = {
        "title": data.title,
        "content": data.content,
        "tags": data.tags,
        "author_id": current_user.id,
    }
    view = await plugin.create_unit(db, kb_id, payload)
    # P17 — 同步产出 chunks（plugin.to_chunk_seeds + chunk_service 持久化）。
    await ChunkService(db).create_chunks_for_unit("entry", view.unit_id, kb_id)
    await db.commit()  # 提交 chunks 后再 enqueue embedding（task 在新 session 读）

    # M3.2 — 异步触发 embedding（让 entry KB 真正可检索）
    from app.knowledge.embedding.tasks import embed_unit_chunks
    from app.core.tasks import safe_delay
    safe_delay(embed_unit_chunks, "entry", str(view.unit_id), str(kb_id))

    entry = await db.get(KnowledgeEntry, view.unit_id)
    logger.info(
        "entry.created",
        kb_id=str(kb_id), unit_id=str(view.unit_id),
        token_count=entry.token_count if entry else 0,
        author=str(current_user.id),
    )
    return (await _build_entry_responses(db, [entry]))[0]


@router.get("", response_model=PaginatedResponse)
async def list_entries(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    folder_id: uuid.UUID | None = Query(None, description="按文件夹过滤；省略=全部"),
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)

    base = select(KnowledgeEntry).where(
        KnowledgeEntry.knowledge_base_id == kb_id,
        KnowledgeEntry.is_archived.is_(False),
    )
    if folder_id is not None:
        base = base.where(KnowledgeEntry.folder_id == folder_id)
    from sqlalchemy import func as sa_func
    total = int((await db.execute(
        select(sa_func.count()).select_from(base.subquery())
    )).scalar() or 0)
    rows = (await db.execute(
        base.order_by(KnowledgeEntry.updated_at.desc())
        .offset(pagination.offset).limit(pagination.page_size)
    )).scalars().all()
    responses = await _build_entry_responses(db, list(rows))
    return PaginatedResponse(
        items=[r.model_dump(mode="json") for r in responses],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{entry_id}", response_model=EntryResponse)
async def get_entry(
    kb_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by)
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None or entry.knowledge_base_id != kb_id:
        raise HTTPException(404, "Entry not found")
    return (await _build_entry_responses(db, [entry]))[0]


@router.post("/{entry_id}/update", response_model=EntryResponse)
async def update_entry(
    kb_id: uuid.UUID,
    entry_id: uuid.UUID,
    data: EntryUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None or entry.knowledge_base_id != kb_id:
        raise HTTPException(404, "Entry not found")

    plugin = get_plugin("entry")
    payload = data.model_dump(exclude_unset=True)
    # plugin.update_unit 已删旧 chunks（如内容变化），这里同步重建
    await plugin.update_unit(db, entry_id, payload)
    existing = (await db.execute(
        select(Chunk.id).where(Chunk.unit_type == "entry", Chunk.unit_id == entry_id).limit(1)
    )).first()
    rechunked = existing is None
    if rechunked:
        await ChunkService(db).create_chunks_for_unit("entry", entry_id, kb_id)
    await db.commit()
    if rechunked:
        # 1. 先清掉 milvus 里旧 chunk 向量，避免检索读到老内容（核心 bugfix）
        await _purge_milvus_for_entries(db, kb_id, [entry_id])
        # 2. 异步 embedding，新 chunks 重新写入 milvus
        from app.knowledge.embedding.tasks import embed_unit_chunks
        from app.core.tasks import safe_delay
        safe_delay(embed_unit_chunks, "entry", str(entry_id), str(kb_id))
    await db.refresh(entry)
    logger.info(
        "entry.updated",
        kb_id=str(kb_id), unit_id=str(entry_id),
        rechunked=rechunked, actor=str(current_user.id),
    )
    return (await _build_entry_responses(db, [entry]))[0]


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_entries(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Plan 41 M3.1 — CSV/JSONL 批量导入条目（异步，返回 task_id）。
    CSV header: title, content, tags（可选，分号或逗号分隔）。
    JSONL: {"title": ..., "content": ..., "tags": [...] }"""
    import base64

    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    if kb.source_type != "entry":
        raise HTTPException(400, "This KB is not entry-type")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    fname = (file.filename or "").lower()
    if fname.endswith(".csv"):
        fmt = "csv"
    elif fname.endswith(".jsonl") or fname.endswith(".ndjson"):
        fmt = "jsonl"
    else:
        raise HTTPException(400, "Only .csv / .jsonl accepted")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5 MB 上限
        raise HTTPException(413, "File too large (max 5 MB)")

    plugin = get_plugin("entry")
    task_id = await plugin.import_batch(db, kb_id, {
        "format": fmt,
        "content_b64": base64.b64encode(content).decode("ascii"),
        "author_id": str(current_user.id),
    })
    logger.info(
        "entry.imported",
        kb_id=str(kb_id), format=fmt, size_bytes=len(content),
        task_id=task_id, actor=str(current_user.id),
    )
    return {"task_id": task_id, "status": "accepted"}


@router.post("/batch/delete")
async def batch_delete_entries(
    kb_id: uuid.UUID,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """批量删除条目。body: {ids: [uuid, ...]} —— 单次最多 100 条。"""
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    ids_raw = body.get("ids") or []
    if not isinstance(ids_raw, list) or not ids_raw:
        raise HTTPException(400, "ids list required")
    if len(ids_raw) > 100:
        raise HTTPException(400, "max 100 ids per batch")
    try:
        entry_ids = [uuid.UUID(str(i)) for i in ids_raw]
    except (ValueError, TypeError):
        raise HTTPException(400, "invalid id format")

    # 一次性删 chunks（多态 unit FK） + entry 行
    await db.execute(
        delete(Chunk).where(Chunk.unit_type == "entry", Chunk.unit_id.in_(entry_ids))
    )
    await db.execute(
        delete(KnowledgeEntry).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            KnowledgeEntry.id.in_(entry_ids),
        )
    )
    await db.commit()
    # 同步清 milvus 旧向量，避免检索仍能命中已删条目（与 file 路径对齐）
    await _purge_milvus_for_entries(db, kb_id, entry_ids)
    logger.info(
        "entry.batch_deleted",
        kb_id=str(kb_id), count=len(entry_ids), actor=str(current_user.id),
    )
    return {"status": "completed", "deleted": len(entry_ids)}


@router.post("/batch/archive")
async def batch_archive_entries(
    kb_id: uuid.UUID,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """批量归档条目（is_archived=True，可逆，仅从列表 / 检索路径过滤掉）。"""
    from sqlalchemy import update as _update
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")

    ids_raw = body.get("ids") or []
    if not isinstance(ids_raw, list) or not ids_raw:
        raise HTTPException(400, "ids list required")
    if len(ids_raw) > 100:
        raise HTTPException(400, "max 100 ids per batch")
    try:
        entry_ids = [uuid.UUID(str(i)) for i in ids_raw]
    except (ValueError, TypeError):
        raise HTTPException(400, "invalid id format")

    await db.execute(
        _update(KnowledgeEntry)
        .where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            KnowledgeEntry.id.in_(entry_ids),
        )
        .values(is_archived=True)
    )
    logger.info(
        "entry.batch_archived",
        kb_id=str(kb_id), count=len(entry_ids), actor=str(current_user.id),
    )
    return {"status": "completed", "archived": len(entry_ids)}


@router.post("/{entry_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    kb_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    await check_resource_access(current_user, "knowledge_base", kb.id, db, kb.created_by, "edit")
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None or entry.knowledge_base_id != kb_id:
        raise HTTPException(404, "Entry not found")

    # 1. plugin 钩子（清理 plugin 独占副产物 — entry 类型无副产物）
    plugin = get_plugin("entry")
    await plugin.on_unit_deleted(db, entry_id)

    # 2. 删 chunks（多态 unit FK；同 file 路径模式）
    await db.execute(
        delete(Chunk).where(Chunk.unit_type == "entry", Chunk.unit_id == entry_id)
    )

    # 3. 删 entry 行
    await db.delete(entry)
    await db.commit()

    # 4. 同步清 milvus 旧向量
    await _purge_milvus_for_entries(db, kb_id, [entry_id])
    logger.info(
        "entry.deleted",
        kb_id=str(kb_id), unit_id=str(entry_id), actor=str(current_user.id),
    )
