"""IngestionPlugin 抽象 — Plan 40 M1 核心契约。

`KnowledgeUnit` 是检索单元的统一抽象（spec `01-knowledge-engine.md`）：
- 物理上没有 knowledge_units 单表
- 按 source_type 落到具体子类型表（documents / knowledge_entries / ...）
- 通过 chunks.unit_type + chunks.unit_id 多态关联

每种 source_type 对应一个 IngestionPlugin 实现：
- file        → FileSourcePlugin（包装现有 ingestion 路径）
- entry       → EntrySourcePlugin（Plan 41）
- git_repo    → 未来 roadmap
- confluence  → 未来 roadmap

下游检索 / 治理代码只与 chunks 打交道，不感知 unit 类型。
加新 KB 类型 = 新建一张 unit 表 + 写一个 Plugin，核心代码零改动。
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class UnitView(BaseModel):
    """管理界面渲染用的 unit 摘要，跨 source_type 统一形态。
    Plugin 从底层表（documents / knowledge_entries / ...）映射到此结构。"""
    unit_type: str
    unit_id: uuid.UUID
    title: str
    subtitle: str | None = None         # 文件型=size+type，条目型=tag 列表
    chunk_count: int = 0
    review_status: str | None = None    # NULL | pending | approved | rejected
    is_archived: bool = False
    is_stale: bool = False
    hit_count_30d: int = 0
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChunkSeed(BaseModel):
    """Plugin 产物：纯文本 + 元信息，**不含 embedding / vector_id**。
    下游统一 embedding pipeline 接管，写 chunks 表 + Milvus。
    metadata schema 同 chunks.metadata（heading / page_number / keywords /
    questions / raptor_children 等，详见 spec 10-data-model.md chunks 行）。"""
    content: str
    parent_chunk_id: uuid.UUID | None = None
    level: int = 0
    position: int
    token_count: int = 0
    folder_id: uuid.UUID | None = None  # 仅 file 型有意义
    metadata: dict | None = None


class PluginCapabilities(TypedDict):
    """Plugin 能力声明，前端按此动态渲染 UI。"""
    supports_inline_edit: bool      # 用户可在线 CRUD（文件型 False，条目型 True）
    supports_folder_tree: bool      # 文件树 UI（文件型 True，条目型 False）
    supports_sync: bool             # 外部源周期 / webhook 同步
    supports_batch_import: bool     # CSV / JSONL / 文件夹批量导入
    ui_layout: Literal["folder_tree", "list_grid", "table"]


class IngestionPlugin(ABC):
    """source_type 对应的具体 plugin。注册到 SOURCE_PLUGINS 后 KB 创建路径
    可按 KB.source_type 找到 plugin。"""

    source_type: str
    capabilities: PluginCapabilities

    # ── 必须实现 ─────────────────────────────────────────────────

    @abstractmethod
    async def list_units(
        self, db: AsyncSession, kb_id: uuid.UUID,
    ) -> list[UnitView]:
        """列出该 KB 下所有 unit，给管理界面用。"""

    @abstractmethod
    async def to_chunk_seeds(
        self, db: AsyncSession, unit: Any,
    ) -> list[ChunkSeed]:
        """把 unit 转成 chunk seeds。仅产出 raw 切片 + 元信息；不写
        chunks 表 / 不算 embedding / 不写 Milvus。下游 chunk_service 接管。"""

    @abstractmethod
    async def mark_stale_units(
        self, db: AsyncSession, kb_id: uuid.UUID, cutoff: datetime,
    ) -> int:
        """治理 lifecycle 钩子：标记过期 unit；返回标记数。
        与 documents lifecycle 两阶段对齐（先 mark stale → 30d idle → archive）。"""

    # ── 按 capability 选实现 ─────────────────────────────────────

    async def create_unit(
        self, db: AsyncSession, kb_id: uuid.UUID, payload: dict,
    ) -> UnitView:
        """supports_inline_edit=True 时实现。"""
        raise NotImplementedError(
            f"{self.source_type} plugin does not support inline edit",
        )

    async def update_unit(
        self, db: AsyncSession, unit_id: uuid.UUID, payload: dict,
    ) -> UnitView:
        raise NotImplementedError(
            f"{self.source_type} plugin does not support inline edit",
        )

    async def on_unit_deleted(
        self, db: AsyncSession, unit_id: uuid.UUID,
    ) -> None:
        """Unit 删除前钩子。清理 plugin 独占副产物（如 MinIO 文件）。
        chunks / Milvus 由 service 层级联清理（cascade_delete_unit task）。"""
        return None

    async def sync(
        self, db: AsyncSession, kb_id: uuid.UUID,
    ) -> str:
        """supports_sync=True 时实现。**异步语义**：触发 celery 任务后立即
        返回 task_id，HTTP 不阻塞。"""
        raise NotImplementedError(
            f"{self.source_type} plugin does not support sync",
        )

    async def import_batch(
        self, db: AsyncSession, kb_id: uuid.UUID, file: Any,
    ) -> str:
        """supports_batch_import=True 时实现，返回 celery task_id。"""
        raise NotImplementedError(
            f"{self.source_type} plugin does not support batch import",
        )
