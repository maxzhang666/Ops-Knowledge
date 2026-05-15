"""EntrySourcePlugin — 条目型 KB 的 IngestionPlugin 实现（Plan 41 M1.3）。

每条 entry 是用户在线编辑的短词条；< 1500 token 一条一 chunk（不切片），
≥ 1500 token 走通用 markdown 切片产出多 chunks（"降级切片"）。

核心差异（vs FileSourcePlugin）：
- supports_inline_edit=True
- supports_folder_tree=False
- supports_batch_import=True (CSV / JSONL)
- ui_layout="table"

import 时自动注册到 SOURCE_PLUGINS。
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


def _content_hash(content: str) -> str:
    """sha256 hex of content; matches alembic 0060 backfill format."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

from app.knowledge.models import Chunk, KnowledgeBase, KnowledgeEntry
from app.knowledge.sources.base import (
    ChunkSeed,
    IngestionPlugin,
    PluginCapabilities,
    UnitView,
)
from app.knowledge.sources.registry import register_plugin

# 降级切片阈值（token 数）。短条目一条一 chunk；超长走 markdown 切片。
# KB 配置可覆盖：KB.chunking_config.entry_chunking_threshold_tokens
DEFAULT_ENTRY_CHUNK_THRESHOLD = 1500


class EntrySourcePlugin(IngestionPlugin):
    source_type = "entry"
    capabilities: PluginCapabilities = {
        "supports_inline_edit": True,
        "supports_folder_tree": False,
        "supports_sync": False,
        "supports_batch_import": True,
        "ui_layout": "table",
    }

    async def list_units(
        self, db: AsyncSession, kb_id: uuid.UUID,
    ) -> list[UnitView]:
        rows = (await db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                KnowledgeEntry.is_archived.is_(False),
            ).order_by(KnowledgeEntry.updated_at.desc())
        )).scalars().all()
        # chunk_count 单独查（聚合 by unit_id）
        entry_ids = [e.id for e in rows]
        chunk_count_map: dict[uuid.UUID, int] = {}
        if entry_ids:
            rows_cnt = (await db.execute(
                select(Chunk.unit_id, func.count(Chunk.id))
                .where(
                    Chunk.unit_type == "entry",
                    Chunk.unit_id.in_(entry_ids),
                )
                .group_by(Chunk.unit_id)
            )).all()
            chunk_count_map = {r[0]: int(r[1]) for r in rows_cnt}
        return [self._to_unit_view(e, chunk_count_map.get(e.id, 0)) for e in rows]

    async def to_chunk_seeds(
        self, db: AsyncSession, unit: KnowledgeEntry,
    ) -> list[ChunkSeed]:
        """降级切片：< 阈值整段一 chunk；≥ 阈值走 markdown 通用切片。
        title / tags 注入每个 seed 的 metadata（embedding 时增强语义）。"""
        kb = await db.get(KnowledgeBase, unit.knowledge_base_id)
        threshold = self._get_threshold(kb)
        meta_base = {"title": unit.title, "tags": unit.tags or []}

        if (unit.token_count or 0) < threshold:
            return [ChunkSeed(
                content=unit.content,
                level=0,
                position=0,
                token_count=unit.token_count or 0,
                metadata=meta_base,
            )]

        # 降级路径：复用 markdown 切片器
        try:
            from app.knowledge.chunking.markdown import MarkdownStrategy
            strategy = MarkdownStrategy()
            # MarkdownStrategy.chunk(text, config) 需要 config 参数；走默认
            results = strategy.chunk(unit.content, config={})
            seeds: list[ChunkSeed] = []
            for i, r in enumerate(results):
                seeds.append(ChunkSeed(
                    content=r.content,
                    level=getattr(r, "level", 0),
                    position=getattr(r, "position", i),
                    token_count=getattr(r, "token_count", 0),
                    metadata={**meta_base, **(getattr(r, "metadata", None) or {})},
                ))
            return seeds
        except Exception:
            # markdown 切片失败 fallback 整段一 chunk（不阻塞主流程）
            return [ChunkSeed(
                content=unit.content,
                level=0, position=0,
                token_count=unit.token_count or 0,
                metadata=meta_base,
            )]

    async def create_unit(
        self, db: AsyncSession, kb_id: uuid.UUID, payload: dict,
    ) -> UnitView:
        """创建条目；review_required=True 时置 pending；触发异步 chunking."""
        kb = await db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError("Knowledge base not found")

        # Spec 25 — 用户标签强制 normalize（命中字典 / 未命中创建 canonical）
        from app.knowledge.tagging.normalizer import normalize_tags
        normalized_tags = await normalize_tags(
            db, kb_id, payload.get("tags") or [],
            allow_create=True, actor_id=payload.get("author_id"),
        )

        now_utc = datetime.now(timezone.utc)
        entry = KnowledgeEntry(
            knowledge_base_id=kb_id,
            folder_id=payload.get("folder_id"),
            title=payload["title"],
            content=payload["content"],
            content_hash=_content_hash(payload["content"]),
            tags=normalized_tags or None,
            token_count=_estimate_tokens(payload["content"]),
            created_by=payload["author_id"],
            # 创建即视为"用户最近一次编辑"
            last_user_edited_at=now_utc,
        )
        if kb.review_required:
            entry.review_status = "pending"
            entry.last_pending_started_at = datetime.now(timezone.utc)
        # Plan 41 状态：刚创建 → processing（chunks 同步生成 + 异步 embed 启动）
        entry.status = "processing"
        db.add(entry)
        await db.flush()
        # async session 下 server_default 字段（created_at/updated_at）flush 后 expired，
        # 必须显式 refresh，否则 _to_unit_view 访问会触发同步 IO → MissingGreenlet
        await db.refresh(entry, attribute_names=["created_at", "updated_at"])
        return self._to_unit_view(entry, chunk_count=0)

    async def update_unit(
        self, db: AsyncSession, unit_id: uuid.UUID, payload: dict,
    ) -> UnitView:
        """编辑条目。任何字段（title/content/tags）变化触发重切 + 重审
        （与 spec `19 §14.1` "所有 unit 编辑提交均置为 pending" 对齐）。"""
        entry = await db.get(KnowledgeEntry, unit_id)
        if entry is None:
            raise ValueError("Entry not found")

        # Spec 25 — tags 在变更检测之前先 normalize（命中字典则 canonical 一致）
        normalized_new_tags: list[str] | None = None
        if "tags" in payload:
            from app.knowledge.tagging.normalizer import normalize_tags
            normalized_new_tags = await normalize_tags(
                db, entry.knowledge_base_id, payload.get("tags") or [],
                allow_create=True,
            )

        # #5 — 用 content_hash 短路 content 字符串比较：仅当新旧 hash 不同
        # 才视为内容物质变化（需要 rechunk + reembed）。tags 仅参与 review
        # state 判定，**不**触发 material_changed —— 标签变化在 retrieval 链
        # 单独走 Milvus update_chunk_tags（见 #244）。
        new_content = payload.get("content", entry.content)
        new_hash = _content_hash(new_content) if "content" in payload else entry.content_hash
        content_changed = (
            "content" in payload
            and (entry.content_hash is None or new_hash != entry.content_hash)
        )
        title_changed = (
            "title" in payload and payload["title"] != entry.title
        )
        tags_changed = (
            normalized_new_tags is not None
            and normalized_new_tags != (entry.tags or [])
        )
        folder_changed = (
            "folder_id" in payload and payload["folder_id"] != entry.folder_id
        )
        # material_changed 仅当 content 真正变化（决定 rechunk + reembed 路径）；
        # title/tags 单独追踪用于 review reset（spec 19 §14.1 "任何字段变化进 review"）；
        # folder_changed 不进 review_relevant（移动文件夹不算"内容编辑"），但仍刷
        # last_user_edited_at（产品视角："我移动了这条目"）。
        material_changed = content_changed
        any_review_relevant_change = content_changed or title_changed or tags_changed
        # 产品视角的"用户操作时间"：覆盖 title / content / tags / folder 任一变化。
        # 用于前端事件流"编辑了内容"展示，与 DB updated_at（被 status / review /
        # lifecycle 等 onupdate 污染）解耦。
        user_edited = (
            content_changed or title_changed or tags_changed or folder_changed
        )

        # 应用字段更新
        if "title" in payload:
            entry.title = payload["title"]
        if "content" in payload:
            entry.content = payload["content"]
            entry.content_hash = new_hash
            entry.token_count = _estimate_tokens(payload["content"])
        if normalized_new_tags is not None:
            entry.tags = normalized_new_tags or None
        if "folder_id" in payload:
            entry.folder_id = payload["folder_id"]
        if user_edited:
            entry.last_user_edited_at = datetime.now(timezone.utc)

        # review_required 的 KB：任何字段变化都重置 review state（spec 19 §14.1）
        if any_review_relevant_change:
            kb = await db.get(KnowledgeBase, entry.knowledge_base_id)
            if kb is not None and kb.review_required:
                entry.review_status = "pending"
                entry.last_pending_started_at = datetime.now(timezone.utc)
                entry.reviewer_id = None
                entry.reviewed_at = None
                entry.review_comment = None

        # rechunk + reembed 仅在 content 真正变化时触发
        if material_changed:
            # 删旧 chunks（待重新切片产出新 chunks）
            await db.execute(
                delete(Chunk).where(
                    Chunk.unit_type == "entry", Chunk.unit_id == unit_id,
                )
            )
            entry.status = "processing"
            entry.error_message = None
        await db.flush()
        # onupdate=func.now() 触发后 updated_at 在 ORM 端 expired，
        # 异步 session 不允许同步 reload，必须显式 refresh
        await db.refresh(entry, attribute_names=["updated_at"])

        chunk_count = int((await db.execute(
            select(func.count(Chunk.id)).where(
                Chunk.unit_type == "entry", Chunk.unit_id == unit_id,
            )
        )).scalar() or 0)
        return self._to_unit_view(entry, chunk_count)

    async def on_unit_deleted(
        self, db: AsyncSession, unit_id: uuid.UUID,
    ) -> None:
        """条目无外部副产物（无 MinIO 文件）。chunks / Milvus 由 service 层
        级联清理（cascade_delete_unit task），plugin 这里仅记 logger。"""
        return None

    async def import_batch(
        self, db: AsyncSession, kb_id: uuid.UUID, file: object,
    ) -> str:
        """Plan 41 M3.1 — 异步批量导入 CSV/JSONL。返回 celery task_id。
        ``file`` 是 dict {format: "csv"|"jsonl", content_b64: str, author_id: str}。"""
        from app.knowledge.sources.entry_tasks import import_entries_batch
        if not isinstance(file, dict):
            raise ValueError("file must be a dict {format, content_b64, author_id}")
        result = import_entries_batch.delay(
            str(kb_id),
            str(file["author_id"]),
            file["format"],
            file["content_b64"],
        )
        return result.id

    async def mark_stale_units(
        self, db: AsyncSession, kb_id: uuid.UUID, cutoff: datetime,
    ) -> int:
        """与 documents lifecycle 两阶段对齐：先 mark stale，archive 由后续
        idle 判定决定（unit_lifecycle 任务负责整体）。"""
        result = await db.execute(
            update(KnowledgeEntry)
            .where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                KnowledgeEntry.is_archived.is_(False),
                KnowledgeEntry.is_stale.is_(False),
                KnowledgeEntry.updated_at < cutoff,
            )
            .values(is_stale=True, stale_since=datetime.now(timezone.utc))
            .returning(KnowledgeEntry.id)
        )
        return len(result.all())

    # ── 内部 ────────────────────────────────────────────────────

    def _get_threshold(self, kb: KnowledgeBase | None) -> int:
        if kb is None:
            return DEFAULT_ENTRY_CHUNK_THRESHOLD
        cfg = kb.chunking_config or {}
        return int(cfg.get(
            "entry_chunking_threshold_tokens", DEFAULT_ENTRY_CHUNK_THRESHOLD,
        ))

    def _to_unit_view(self, entry: KnowledgeEntry, chunk_count: int) -> UnitView:
        # subtitle: tags 列表（最多 3 个）
        tags = entry.tags or []
        subtitle = " · ".join(tags[:3]) if tags else None
        return UnitView(
            unit_type="entry",
            unit_id=entry.id,
            title=entry.title,
            subtitle=subtitle,
            chunk_count=chunk_count,
            review_status=entry.review_status,
            is_archived=entry.is_archived,
            is_stale=entry.is_stale,
            hit_count_30d=0,  # 治理动态分将来通过 chunks 聚合补
            created_by=entry.created_by,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


def _estimate_tokens(text: str) -> int:
    """轻量 token 估算：按 ~3 字符 = 1 token（中文 1 字 ≈ 1 token，
    英文 ~4 字符 = 1 token，中英混合取折中）。
    精确分词由 chunk_service 内的 token 计数负责，这里仅估算用于阈值判定。"""
    return max(1, len(text) // 3)


# import 时自动注册到 SOURCE_PLUGINS
register_plugin(EntrySourcePlugin())
