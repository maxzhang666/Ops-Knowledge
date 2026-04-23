import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Agent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="simple"
    )

    knowledge_base_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    folder_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    model_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id"), nullable=True
    )
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True
    )

    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB list of quick-prompt strings shown as clickable hint chips in Chat.
    # Nullable = "author hasn't configured any" (we also treat []  as empty).
    suggested_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    show_thinking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    thinking_detail: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="normal"
    )
    no_result_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="honest"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
