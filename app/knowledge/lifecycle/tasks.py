"""Document lifecycle Celery tasks (Plan 32 M3).

Daily beat ``document_lifecycle``:
  1. For each active KB, read ``governance_config`` (expiration_threshold_days,
     auto_archive_idle_days) with system defaults.
  2. Sweep non-archived documents, compute staleness:
       - ``updated_at < now − expiration_days``  (primary signal)
       - ``hits_7d < hits_prev_7d × 0.3``        (heat cliff signal)
  3. Transition logic (all idempotent):
       - False → True  : set ``is_stale=True, stale_since=now``, emit Notification
                         to owner + dept_admins (once per transition).
       - True  → False : clear flags — owner re-engaged, reset cycle.
       - True + ``stale_since < now − idle_days`` → auto-archive + notify.

The heat cliff check is computed per KB via one SQL sweep joining
``chunks`` × ``chunk_usage_events`` so the task stays O(KBs), not O(docs).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = structlog.get_logger(__name__)


DEFAULT_EXPIRATION_DAYS = 90
DEFAULT_AUTO_ARCHIVE_IDLE_DAYS = 30
HIT_DROP_RATIO = 0.3   # "rolling_hit_7d < rolling_hit_prev_7d × 0.3"


@shared_task(name="app.knowledge.lifecycle.tasks.document_lifecycle")
def document_lifecycle() -> dict:
    """Plan 32 M3 — 文件型 lifecycle。
    Plan 40 M2 — deprecated alias，保持向后兼容（celery beat schedule 一个版本周期内）；
    新代码用 ``unit_lifecycle``。"""
    return asyncio.run(_run_lifecycle())


@shared_task(name="app.knowledge.lifecycle.tasks.unit_lifecycle")
def unit_lifecycle() -> dict:
    """Plan 40 M2 — 通用 lifecycle 任务，按 KB.source_type 路由到对应 plugin。
    当前文件型仍走 _run_lifecycle 现有路径；非 file 类型 (Plan 41 entry 等) 走
    IngestionPlugin.mark_stale_units。"""
    return asyncio.run(_run_lifecycle())


async def _run_lifecycle(now: datetime | None = None) -> dict:
    from app.department.models import DepartmentRole, UserDepartment
    from app.knowledge.governance.models import ChunkUsageEvent
    from app.knowledge.models import Chunk, Document, KnowledgeBase
    from app.system.models import Notification

    now = now or datetime.now(timezone.utc)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"kbs": 0, "new_stale": 0, "cleared_stale": 0, "archived": 0, "notifications": 0}
    try:
        async with sm() as db:
            kbs = (await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.status == "active")
            )).scalars().all()

            for kb in kbs:
                stats["kbs"] += 1
                # Plan 40 M2 — 非 file 类型 KB 通过 plugin 接口处理 lifecycle
                # （Plan 41 entry 等）。当前文件型仍走下方现有 documents 路径。
                if kb.source_type != "file":
                    try:
                        from app.knowledge.sources import get_plugin
                        plugin = get_plugin(kb.source_type)
                        cfg2 = kb.governance_config or {}
                        cutoff_p = now - timedelta(
                            days=int(cfg2.get("expiration_threshold_days", DEFAULT_EXPIRATION_DAYS)),
                        )
                        marked = await plugin.mark_stale_units(db, kb.id, cutoff_p)
                        stats["new_stale"] += marked
                    except Exception:
                        logger.debug("plugin_mark_stale_failed", kb_id=str(kb.id), exc_info=True)
                    continue

                cfg = kb.governance_config or {}
                expiration_days = int(cfg.get("expiration_threshold_days", DEFAULT_EXPIRATION_DAYS))
                idle_days = int(cfg.get("auto_archive_idle_days", DEFAULT_AUTO_ARCHIVE_IDLE_DAYS))
                stale_cutoff = now - timedelta(days=expiration_days)
                archive_cutoff = now - timedelta(days=idle_days)

                hit_map = await _compute_doc_hit_windows(db, kb.id, now)

                docs = (await db.execute(
                    select(Document).where(
                        Document.knowledge_base_id == kb.id,
                        Document.is_archived.is_(False),
                    )
                )).scalars().all()

                for doc in docs:
                    hits7, hits_prev7 = hit_map.get(doc.id, (0, 0))
                    updated_stale = doc.updated_at < stale_cutoff
                    heat_cliff = hits_prev7 > 0 and hits7 < hits_prev7 * HIT_DROP_RATIO
                    should_be_stale = updated_stale or heat_cliff

                    if should_be_stale and not doc.is_stale:
                        # False → True — mark + notify once
                        doc.is_stale = True
                        doc.stale_since = now
                        stats["new_stale"] += 1
                        notified = await _notify_stale(
                            db, Notification,
                            doc=doc, kb=kb, updated_stale=updated_stale, heat_cliff=heat_cliff,
                            dept_admin_cls=UserDepartment, dept_role_enum=DepartmentRole,
                        )
                        stats["notifications"] += notified

                    elif not should_be_stale and doc.is_stale:
                        # True → False — owner re-engaged, reset cycle
                        doc.is_stale = False
                        doc.stale_since = None
                        stats["cleared_stale"] += 1

                    elif doc.is_stale and doc.stale_since is not None and doc.stale_since < archive_cutoff:
                        # Auto-archive — stale long enough, idle per cfg
                        doc.is_archived = True
                        stats["archived"] += 1
                        notified = await _notify_archived(
                            db, Notification, doc=doc, kb=kb,
                            dept_admin_cls=UserDepartment, dept_role_enum=DepartmentRole,
                        )
                        stats["notifications"] += notified

            await db.commit()
        logger.info("document_lifecycle_done", **stats)
        return stats
    finally:
        await engine.dispose()


async def _compute_doc_hit_windows(
    db: AsyncSession, kb_id: uuid.UUID, now: datetime,
) -> dict[uuid.UUID, tuple[int, int]]:
    """One SQL sweep per KB — returns {doc_id: (hits_7d, hits_prev_7d)}.

    Only docs with at least one hit in the last 14d appear; absent docs
    are treated as (0, 0) by the caller.
    """
    from app.knowledge.governance.models import ChunkUsageEvent
    from app.knowledge.models import Chunk

    t_7d = now - timedelta(days=7)
    t_14d = now - timedelta(days=14)
    # Plan 40 M2 — 多态 unit FK 切读：仅文件型 KB 有 documents，按 unit_type 限定
    rows = (await db.execute(
        select(
            Chunk.unit_id,
            func.sum(case((ChunkUsageEvent.created_at >= t_7d, 1), else_=0)).label("hits7"),
            func.sum(
                case(
                    (
                        and_(
                            ChunkUsageEvent.created_at >= t_14d,
                            ChunkUsageEvent.created_at < t_7d,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("hits_prev7"),
        )
        .select_from(ChunkUsageEvent)
        .join(Chunk, Chunk.id == ChunkUsageEvent.chunk_id)
        .where(
            Chunk.knowledge_base_id == kb_id,
            Chunk.unit_type == "document",
            Chunk.review_excluded.is_(False),
            ChunkUsageEvent.event_type == "hit",
            ChunkUsageEvent.created_at >= t_14d,
        )
        .group_by(Chunk.unit_id)
    )).all()
    return {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in rows}


async def _dept_admin_ids(
    db: AsyncSession, user_id: uuid.UUID, dept_cls, role_enum,
) -> list[uuid.UUID]:
    """Department admins in any department the given user belongs to.

    Excludes the user themselves — they already get the owner notification.
    """
    dept_ids = (await db.execute(
        select(dept_cls.department_id).where(dept_cls.user_id == user_id)
    )).scalars().all()
    if not dept_ids:
        return []
    admin_rows = (await db.execute(
        select(dept_cls.user_id).distinct().where(
            dept_cls.department_id.in_(dept_ids),
            dept_cls.role == role_enum.DEPT_ADMIN,
        )
    )).scalars().all()
    return [u for u in admin_rows if u != user_id]


async def _notify_stale(
    db: AsyncSession, notif_cls, *, doc, kb,
    updated_stale: bool, heat_cliff: bool,
    dept_admin_cls, dept_role_enum,
) -> int:
    reason = []
    if updated_stale:
        reason.append("长时间未更新")
    if heat_cliff:
        reason.append("近 7 天检索量骤降")
    title = f"文档「{doc.title}」已过期（{'、'.join(reason)}）"
    content = (
        f"知识库「{kb.name}」下的文档「{doc.title}」被标记为过期。"
        "请评估是否需要更新内容或允许系统自动归档。"
    )
    targets = {doc.created_by}
    targets.update(await _dept_admin_ids(db, doc.created_by, dept_admin_cls, dept_role_enum))
    count = 0
    for uid in targets:
        db.add(notif_cls(
            user_id=uid,
            type="document_stale",
            title=title,
            content=content,
            priority="normal",
            resource_type="document",
            resource_id=doc.id,
        ))
        count += 1
    return count


async def _notify_archived(
    db: AsyncSession, notif_cls, *, doc, kb,
    dept_admin_cls, dept_role_enum,
) -> int:
    title = f"文档「{doc.title}」已自动归档"
    content = (
        f"知识库「{kb.name}」下的文档「{doc.title}」因长时间未更新且未被使用，"
        "已自动归档。归档后不再参与检索，可随时恢复。"
    )
    targets = {doc.created_by}
    targets.update(await _dept_admin_ids(db, doc.created_by, dept_admin_cls, dept_role_enum))
    count = 0
    for uid in targets:
        db.add(notif_cls(
            user_id=uid,
            type="document_archived",
            title=title,
            content=content,
            priority="normal",
            resource_type="document",
            resource_id=doc.id,
        ))
        count += 1
    return count
