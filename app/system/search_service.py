"""Global cross-domain search (Plan 34 M1).

简单策略：PostgreSQL ILIKE 撒网 + 权限可见性过滤，返回每个域的 Top-N。
不引入 tsvector 全文索引（spec 14 性能层在 Plan 4+ 才考虑）。

可见性：
  * KB        —— 仅返回 created_by==current_user 的 KB（v1 简化；
                后续可接入 department-level access matrix）
  * Document  —— 同 KB 可见 + Document.is_archived=False
  * Conversation —— 仅当前用户的会话

排序：
  * 标题/名称完全匹配 > 标题前缀 > 标题包含 > 描述/内容包含
  * 同等匹配下按更新时间倒序
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import Conversation
from app.knowledge.models import Document, KnowledgeBase


@dataclass
class SearchHit:
    kind: str           # "kb" | "document" | "conversation"
    id: str
    title: str
    subtitle: str       # description / parent KB / etc.
    href: str           # frontend 跳转链接


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        *,
        user_id: uuid.UUID,
        limit_per_domain: int = 8,
    ) -> dict[str, list[SearchHit]]:
        q = (query or "").strip()
        if len(q) < 2:
            return {"kbs": [], "documents": [], "conversations": []}
        like = f"%{q}%"

        return {
            "kbs": await self._search_kbs(q, like, user_id, limit_per_domain),
            "documents": await self._search_documents(q, like, user_id, limit_per_domain),
            "conversations": await self._search_conversations(
                q, like, user_id, limit_per_domain,
            ),
        }

    async def _search_kbs(
        self, q: str, like: str, user_id: uuid.UUID, limit: int,
    ) -> list[SearchHit]:
        rank = case(
            (KnowledgeBase.name.ilike(q), 0),
            (KnowledgeBase.name.ilike(f"{q}%"), 1),
            (KnowledgeBase.name.ilike(like), 2),
            else_=3,
        )
        rows = (await self.db.execute(
            select(KnowledgeBase, rank.label("rank"))
            .where(
                KnowledgeBase.created_by == user_id,
                or_(
                    KnowledgeBase.name.ilike(like),
                    KnowledgeBase.description.ilike(like),
                ),
            )
            .order_by("rank", desc(KnowledgeBase.updated_at))
            .limit(limit)
        )).all()
        return [
            SearchHit(
                kind="kb", id=str(r[0].id),
                title=r[0].name,
                subtitle=(r[0].description or "")[:120],
                href=f"/knowledge/{r[0].id}",
            )
            for r in rows
        ]

    async def _search_documents(
        self, q: str, like: str, user_id: uuid.UUID, limit: int,
    ) -> list[SearchHit]:
        rank = case(
            (Document.title.ilike(q), 0),
            (Document.title.ilike(f"{q}%"), 1),
            else_=2,
        )
        rows = (await self.db.execute(
            select(Document, KnowledgeBase.name.label("kb_name"), rank.label("rank"))
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(
                KnowledgeBase.created_by == user_id,
                Document.is_archived.is_(False),
                Document.title.ilike(like),
            )
            .order_by("rank", desc(Document.updated_at))
            .limit(limit)
        )).all()
        return [
            SearchHit(
                kind="document", id=str(r[0].id),
                title=r[0].title,
                subtitle=f"KB · {r[1]}",
                # 文档详情通过 KB 详情页选中文档 (?doc=) 实现深链
                href=f"/knowledge/{r[0].knowledge_base_id}?doc={r[0].id}",
            )
            for r in rows
        ]

    async def _search_conversations(
        self, q: str, like: str, user_id: uuid.UUID, limit: int,
    ) -> list[SearchHit]:
        rank = case(
            (Conversation.title.ilike(q), 0),
            (Conversation.title.ilike(f"{q}%"), 1),
            else_=2,
        )
        rows = (await self.db.execute(
            select(Conversation, rank.label("rank"))
            .where(
                Conversation.user_id == user_id,
                Conversation.title.isnot(None),
                Conversation.title.ilike(like),
            )
            .order_by("rank", desc(Conversation.updated_at))
            .limit(limit)
        )).all()
        return [
            SearchHit(
                kind="conversation", id=str(r[0].id),
                title=r[0].title or "(无标题)",
                subtitle="",
                href=f"/agents/{r[0].agent_id}?conv={r[0].id}",
            )
            for r in rows
        ]
