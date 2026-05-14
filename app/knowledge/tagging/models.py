"""Spec 25 — Tag-Driven Retrieval Enhancement，字典 / 审计 / KB 设置三表。

字典 (tag_dictionary)：KB 维度 canonical + aliases，标签规范化的真相源。
审计 (tag_dictionary_audit)：所有字典操作（create/rename/merge/split/delete/set_aliases）
留痕，配合异步回填任务实现可回滚的字典治理。
KB 设置 (kb_tag_settings)：每 KB 一份的标签功能配置 + 三档 preset。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class TagDictionary(Base, UUIDMixin):
    """KB 维度的标签字典；canonical 是真名，aliases 是别名数组。

    normalize_tag() 命中 canonical 或 aliases 都返回 canonical。
    is_deprecated=true 时不参与自动提取但保留历史检索路径。
    usage_count 由 daily celery beat 重算（avoid hot-path writes）。
    """
    __tablename__ = "tag_dictionary"
    __table_args__ = (
        # canonical 在 KB 内唯一（lower 比较交给查询层做，PG 简单 unique 索引）
        UniqueConstraint("kb_id", "canonical", name="uq_tag_dict_kb_canonical"),
    )

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    canonical: Mapped[str] = mapped_column(String(64), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    is_deprecated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class TagDictionaryAudit(Base, UUIDMixin):
    """字典操作审计 —— admin 行为留痕，配套异步回填 task 实现可回滚治理。

    op ∈ {'create', 'rename', 'merge', 'split', 'delete', 'set_aliases'}
    before/after 是 JSONB 快照，affected_entries 在异步回填完成后写入。
    """
    __tablename__ = "tag_dictionary_audit"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 单表删除时 dict_id 为 null（before 快照中保留 id）
    dict_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    op: Mapped[str] = mapped_column(String(20), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    affected_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class AutoTagAction(Base, UUIDMixin):
    """Spec 25 Plan E — 自动标签 accept/reject 审计日志。

    每次用户在编辑器点 ✓ accept 或 × reject auto_tag 写入一条记录，
    供 governance 聚合接受率指标（accept / (accept + reject)）。
    """
    __tablename__ = "auto_tag_actions"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    # action: 'accept' | 'reject'
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # source: 'keybert' | 'llm' | 'hybrid' | 'unknown'（被接受/拒绝时来源的提取器）
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class KBTagSettings(Base):
    """KB 级标签功能配置 —— 独立表避免 KB.tag_config JSONB 混乱。

    preset 是预设档（low_cost / balanced / high_quality / custom），具体值映射
    在 service 层 PRESET_VALUES 字典；custom = 用户改过某项后自动落档。
    """
    __tablename__ = "kb_tag_settings"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preset: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="balanced",
    )
    auto_tag_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )
    auto_tag_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="hybrid",
    )
    auto_tag_llm_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_registry.id", ondelete="SET NULL"),
        nullable=True,
    )
    auto_tag_max_per_unit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5",
    )
    auto_tag_confidence_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.6",
    )
    tag_filter_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )
    tag_boost_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.05",
    )
    tag_routing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )
