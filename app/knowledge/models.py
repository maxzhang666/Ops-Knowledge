import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TimestampMixin, UUIDMixin


class KBStatus(str, enum.Enum):
    ACTIVE = "active"
    INDEXING = "indexing"
    ERROR = "error"
    DELETING = "deleting"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class KnowledgeBase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id"), nullable=True
    )
    embedding_model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True
    )
    chunking_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retrieval_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Plan 32 M3 — per-KB lifecycle policy:
    #   { "expiration_threshold_days": int, "auto_archive_idle_days": int }
    # NULL → system defaults
    governance_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Plan 29 — knowledge review workflow opt-in. False keeps legacy behavior.
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Plan 40 M1 — 决定 IngestionPlugin。建库后不可改（unit 数据形态固定）
    source_type: Mapped[str] = mapped_column(
        String(20), default="file", nullable=False, server_default="file"
    )
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Plan 32 M2 健康分缓存（0-100）— 列表 API 零额外查询。
    # NULL = 从未计算过；写回触发点见 governance/service.py compute_health。
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_score_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[KBStatus] = mapped_column(
        Enum(KBStatus, name="kb_status", values_callable=lambda e: [x.value for x in e]), default=KBStatus.ACTIVE, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    folders: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class Folder(Base, UUIDMixin):
    __tablename__ = "folders"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="folders")
    children: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped["Folder | None"] = relationship(
        "Folder", back_populates="children", remote_side="Folder.id"
    )
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="folder")


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda e: [x.value for x in e]), default=DocumentStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Plan 32 M3 生命周期：过期标记 + 标记时间戳，驱动自动归档/通知去重
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Plan 29 — review workflow. NULL = no review required (legacy / KB toggled off);
    # otherwise: pending | approved | rejected.
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plan 39 M2 — 通知去重锚点：进入 pending 时 reset；
    # should_notify_review_pending() 查 notifications.created_at > 此值 决定是否重发
    last_pending_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="documents")
    folder: Mapped["Folder | None"] = relationship("Folder", back_populates="documents")
    # Plan 40 M3 — chunks 反向关系移除（document_id FK 已 drop，
    # cascade 改走 chunks.knowledge_base_id ON DELETE CASCADE，service 层手动
    # DELETE chunks WHERE unit_type='document' AND unit_id=doc.id）


class KnowledgeEntry(Base, UUIDMixin, TimestampMixin):
    """Plan 41 — 条目型 KB 独占。每条 entry 是用户在线编辑的短词条
    (FAQ / SOP / 客服话术)。检索路径与文件型一致（chunks 表多态 FK 关联）。"""
    __tablename__ = "knowledge_entries"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Plan 41 — 条目目录化：复用 folders 表。NULL = 根目录
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0",
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    # Plan 41 — 条目处理状态：pending → processing → completed / error
    # 跟用户看的"条目可检索"的过程同步
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plan 32 M3 lifecycle 两阶段（与 documents 对齐）
    is_stale: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    stale_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Plan 29 review 字段（镜像 documents）
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plan 39 通知去重锚点
    last_pending_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Spec 25 — 自动标签：[{tag, confidence, source, extracted_at}]
    auto_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Spec 25 — 用户拒绝过的自动标签黑名单（下次提取跳过）
    rejected_auto_tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Plan 40 M3 — chunks 多态 FK 已切换：unit_type + unit_id 替代 document_id。
    # document_id 列已 drop（migration 0052），SA model 不再保留该字段。
    # 删除 unit 时由 cascade_delete_unit celery task 处理 chunks 清理。
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edit_history: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    # Plan 32 M1 — dynamic-score denormalized rollup columns; rebuilt by
    # Celery batch (app.knowledge.governance.tasks.chunk_score_rebuild).
    adopted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    feedback_positive: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    feedback_negative: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    quality_dynamic: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_composite: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_adopted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Plan 39 M1 — 审核期内容隔离派生列。pending unit 的 chunks 置 true，
    # 不参与召回 / 命中统计 / 治理动态分。由 ReviewService 维护。
    review_excluded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    # Spec 25 — 标签数组拍平到独立字段（非 metadata 嵌套），便于 GIN 索引 +
    # milvus array filter，避免 JSONB 慢路径。由 chunk_service 在 create/update
    # 时从 entry.tags ∪ filtered(auto_tags) 同步写入。
    chunk_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase")
    parent_chunk: Mapped["Chunk | None"] = relationship("Chunk", remote_side="Chunk.id")
