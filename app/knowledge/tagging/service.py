"""Spec 25 §4 — 字典治理服务。

提供 admin / KB owner 的字典 CRUD + merge/rename/delete + 审计写入。
异步回填（merge / rename 改写所有 entries.tags + chunks.chunk_tags + invalidate cache）
由 app/knowledge/tagging/tasks.py 承担。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.tagging.canonical_cache import (
    invalidate_canonical_embeddings,
)
from app.knowledge.tagging.models import TagDictionary, TagDictionaryAudit
from app.knowledge.tagging.normalizer import invalidate_kb_dict_cache


def _invalidate_all(kb_id) -> None:
    """字典写操作后清两层缓存：lookup map + canonical embedding cache。"""
    invalidate_kb_dict_cache(kb_id)
    invalidate_canonical_embeddings(kb_id)

logger = structlog.get_logger(__name__)


class TagDictionaryService:
    """KB 维度的字典治理。所有写操作必须产生 audit。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 查询 ─────────────────────────────────────────────────────

    async def list(
        self,
        kb_id: uuid.UUID,
        *,
        search: str | None = None,
        include_deprecated: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[TagDictionary], int]:
        base = select(TagDictionary).where(TagDictionary.kb_id == kb_id)
        if not include_deprecated:
            base = base.where(TagDictionary.is_deprecated.is_(False))
        if search:
            like = f"%{search.lower()}%"
            base = base.where(
                or_(
                    func.lower(TagDictionary.canonical).like(like),
                    TagDictionary.aliases.cast(str).like(like),
                )
            )
        total = int((await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0)
        rows = (await self.db.execute(
            base.order_by(TagDictionary.usage_count.desc(), TagDictionary.canonical)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()
        return list(rows), total

    async def get(self, dict_id: uuid.UUID) -> TagDictionary | None:
        return await self.db.get(TagDictionary, dict_id)

    # ── 写入操作（均产生 audit）──────────────────────────────────

    async def create(
        self,
        kb_id: uuid.UUID,
        canonical: str,
        aliases: list[str] | None,
        actor_id: uuid.UUID | None,
    ) -> TagDictionary:
        row = TagDictionary(
            kb_id=kb_id,
            canonical=canonical.strip()[:64],
            aliases=aliases or [],
            created_by=actor_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self._audit(
            kb_id=kb_id, dict_id=row.id, op="create",
            before=None,
            after={"canonical": row.canonical, "aliases": row.aliases},
            actor_id=actor_id,
        )
        _invalidate_all(kb_id)
        return row

    async def set_aliases(
        self,
        dict_id: uuid.UUID,
        aliases: list[str],
        actor_id: uuid.UUID | None,
    ) -> TagDictionary:
        row = await self.db.get(TagDictionary, dict_id)
        if row is None:
            raise ValueError("Dictionary entry not found")
        before = {"aliases": list(row.aliases or [])}
        row.aliases = [a.strip() for a in aliases if a and a.strip()]
        await self.db.flush()
        await self._audit(
            kb_id=row.kb_id, dict_id=row.id, op="set_aliases",
            before=before, after={"aliases": row.aliases},
            actor_id=actor_id,
        )
        _invalidate_all(row.kb_id)
        return row

    async def rename(
        self,
        dict_id: uuid.UUID,
        new_canonical: str,
        actor_id: uuid.UUID | None,
    ) -> tuple[TagDictionary, str]:
        """改名：旧 canonical 进 aliases，新 canonical 生效；返回 (row, old_canonical)。
        调用方负责异步触发 backfill_tag_rename 回填 entries.tags / chunks.chunk_tags。"""
        row = await self.db.get(TagDictionary, dict_id)
        if row is None:
            raise ValueError("Dictionary entry not found")
        old = row.canonical
        new = new_canonical.strip()[:64]
        if not new or new == old:
            return row, old
        aliases = list(row.aliases or [])
        if old not in aliases:
            aliases.append(old)
        before = {"canonical": old, "aliases": list(row.aliases or [])}
        row.canonical = new
        row.aliases = aliases
        await self.db.flush()
        await self._audit(
            kb_id=row.kb_id, dict_id=row.id, op="rename",
            before=before,
            after={"canonical": new, "aliases": aliases},
            actor_id=actor_id,
        )
        _invalidate_all(row.kb_id)
        return row, old

    async def merge(
        self,
        source_ids: list[uuid.UUID],
        target_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> tuple[TagDictionary, list[str]]:
        """合并：sources 的 canonical+aliases 全部并入 target.aliases，sources 软删除。
        返回 (target, list_of_source_canonicals) 供异步回填使用。"""
        target = await self.db.get(TagDictionary, target_id)
        if target is None:
            raise ValueError("Target dictionary entry not found")
        sources = (await self.db.execute(
            select(TagDictionary).where(TagDictionary.id.in_(source_ids))
        )).scalars().all()
        if not sources:
            return target, []
        # 验证同 KB
        for s in sources:
            if s.kb_id != target.kb_id:
                raise ValueError("Cannot merge across knowledge bases")
            if s.id == target.id:
                raise ValueError("Source cannot equal target")

        before_target = {"aliases": list(target.aliases or [])}
        merged_aliases = list(target.aliases or [])
        source_canonicals: list[str] = []
        for s in sources:
            if s.canonical not in merged_aliases:
                merged_aliases.append(s.canonical)
            for a in (s.aliases or []):
                if a not in merged_aliases:
                    merged_aliases.append(a)
            source_canonicals.append(s.canonical)
            s.is_deprecated = True

        target.aliases = merged_aliases
        await self.db.flush()
        await self._audit(
            kb_id=target.kb_id, dict_id=target.id, op="merge",
            before={
                "target": before_target,
                "sources": [
                    {"id": str(s.id), "canonical": s.canonical, "aliases": s.aliases}
                    for s in sources
                ],
            },
            after={
                "target_canonical": target.canonical,
                "merged_aliases": merged_aliases,
            },
            actor_id=actor_id,
        )
        _invalidate_all(target.kb_id)
        return target, source_canonicals

    async def soft_delete(
        self,
        dict_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> TagDictionary:
        row = await self.db.get(TagDictionary, dict_id)
        if row is None:
            raise ValueError("Dictionary entry not found")
        if row.is_deprecated:
            return row
        before = {"canonical": row.canonical, "is_deprecated": False}
        row.is_deprecated = True
        await self.db.flush()
        await self._audit(
            kb_id=row.kb_id, dict_id=row.id, op="delete",
            before=before, after={"is_deprecated": True},
            actor_id=actor_id,
        )
        _invalidate_all(row.kb_id)
        return row

    # ── 审计 ─────────────────────────────────────────────────────

    async def _audit(
        self,
        *,
        kb_id: uuid.UUID,
        dict_id: uuid.UUID | None,
        op: str,
        before: dict | None,
        after: dict | None,
        actor_id: uuid.UUID | None,
    ) -> None:
        self.db.add(TagDictionaryAudit(
            kb_id=kb_id,
            dict_id=dict_id,
            op=op,
            before=before,
            after=after,
            actor_id=actor_id,
        ))
        await self.db.flush()

    async def update_affected_entries(
        self, audit_id: uuid.UUID, count: int,
    ) -> None:
        """异步回填任务完成后更新 audit 行的 affected_entries 数。"""
        await self.db.execute(
            update(TagDictionaryAudit)
            .where(TagDictionaryAudit.id == audit_id)
            .values(affected_entries=count)
        )
        await self.db.flush()

    async def list_audit(
        self,
        kb_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[TagDictionaryAudit], int]:
        base = select(TagDictionaryAudit).where(TagDictionaryAudit.kb_id == kb_id)
        total = int((await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0)
        rows = (await self.db.execute(
            base.order_by(TagDictionaryAudit.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return list(rows), total


# 类型别名供 router 使用：当前 datetime import 未使用，保留以便后续 audit 扩展
_ = datetime  # noqa: F841
_ = timezone  # noqa: F841
