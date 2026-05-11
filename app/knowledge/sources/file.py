"""FileSourcePlugin — 文件型 KB 的 IngestionPlugin 实现（Plan 40 M1.4）。

包装现有 ingestion / chunking / lifecycle 路径，把"文件型独占的实现细节"
封装成 plugin。检索 / 治理代码不直接调本插件，仅通过 registry 取它做：
- list_units（管理界面渲染 docs 列表为 UnitView）
- to_chunk_seeds（让 chunk_service 走通用 embedding pipeline）
- on_unit_deleted（清理 MinIO 对象）
- mark_stale_units（lifecycle 任务）

import 时自动注册到 SOURCE_PLUGINS。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import Document
from app.knowledge.sources.base import (
    ChunkSeed,
    IngestionPlugin,
    PluginCapabilities,
    UnitView,
)
from app.knowledge.sources.registry import register_plugin


class FileSourcePlugin(IngestionPlugin):
    source_type = "file"
    capabilities: PluginCapabilities = {
        # chunk 级编辑（split / merge / edit）已支持，但 unit 级（整文件）
        # 在线编辑不支持 —— 用户要修改文件得重新上传新版本。
        "supports_inline_edit": False,
        "supports_folder_tree": True,
        "supports_sync": False,
        "supports_batch_import": True,   # 现有的多文件批量上传
        "ui_layout": "folder_tree",
    }

    async def list_units(
        self, db: AsyncSession, kb_id: uuid.UUID,
    ) -> list[UnitView]:
        rows = (await db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.is_archived.is_(False),
            ).order_by(Document.created_at.desc())
        )).scalars().all()
        return [self._to_unit_view(d) for d in rows]

    async def to_chunk_seeds(
        self, db: AsyncSession, unit: Any,
    ) -> list[ChunkSeed]:
        """文件型 chunk_seeds 通过现有 chunking 路径产出。

        当前实现：返回空列表占位 —— 实际文件型 chunking 在
        ingestion/tasks.py 中通过 celery 任务 + chunking strategies 完成，
        chunks 由 chunk_service 持久化。Plan 40 M2 切读路径时把 chunking
        路径迁过来；M1 阶段 plugin 仅作为"已注册"标志，实际产出仍走旧流水线。
        """
        return []

    async def on_unit_deleted(
        self, db: AsyncSession, unit_id: uuid.UUID,
    ) -> None:
        """清理 MinIO 对象（plugin 独占副产物）。
        chunks / Milvus 由 service 层级联清理（cascade_delete_unit task）。"""
        doc = await db.get(Document, unit_id)
        if doc is None or not doc.file_path:
            return
        try:
            from app.knowledge.storage.minio_service import MinIOService
            await MinIOService().delete(doc.file_path)
        except Exception:
            # MinIO 删除失败不阻塞 unit 删除主流程；consistency_scan 会兜底
            pass

    async def mark_stale_units(
        self, db: AsyncSession, kb_id: uuid.UUID, cutoff: datetime,
    ) -> int:
        """Plan 32 M3 lifecycle 两阶段第一步：mark stale。
        现有 documents.is_stale / stale_since 字段已存在，直接 UPDATE。"""
        result = await db.execute(
            update(Document)
            .where(
                Document.knowledge_base_id == kb_id,
                Document.is_archived.is_(False),
                Document.is_stale.is_(False),
                Document.updated_at < cutoff,
            )
            .values(is_stale=True, stale_since=datetime.now(timezone.utc))
            .returning(Document.id)
        )
        return len(result.all())

    def _to_unit_view(self, doc: Document) -> UnitView:
        # subtitle: file_size + source_type 简短摘要
        size_kb = (doc.file_size or 0) // 1024 if doc.file_size else 0
        subtitle = f"{doc.source_type or 'file'} · {size_kb} KB"
        return UnitView(
            unit_type="document",
            unit_id=doc.id,
            title=doc.title,
            subtitle=subtitle,
            chunk_count=doc.chunk_count or 0,
            review_status=doc.review_status,
            is_archived=doc.is_archived,
            is_stale=doc.is_stale,
            hit_count_30d=0,  # M2 接入 chunks 聚合
            created_by=doc.created_by,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


# import 时自动注册 —— main.py 启动 import sources/ 即触发
register_plugin(FileSourcePlugin())
