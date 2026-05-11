import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class ModelProvider(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_providers"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-specific extras: api_version (Azure), aws_region (Bedrock), ...
    extra_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    models_available: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class ModelRegistryEntry(Base, UUIDMixin):
    __tablename__ = "model_registry"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Milvus 治理面板：比对 KB 当前 embedding 模型维度 ≟ milvus collection 实际维度。
    # 第一次 embed 时由 embed task 写入；切换模型/未 embed 过的 entry 为 NULL。
    vector_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CostRecord(Base, UUIDMixin):
    __tablename__ = "cost_records"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    call_type: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
