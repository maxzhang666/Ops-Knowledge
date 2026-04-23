import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class MCPServer(Base, UUIDMixin, TimestampMixin):
    """A system-level MCP server configuration.

    ``transport_type`` picks which shape ``config`` / ``auth_config`` take;
    see ``app.mcp.schemas`` for per-transport validation. ``enabled_tools``
    gates which discovered tools are exposed to Agents (null = all,
    [] = none, [...] = whitelist).
    """
    __tablename__ = "mcp_servers"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    auth_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled_tools: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_tools: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class MCPToolCall(Base, UUIDMixin):
    """Audit entry for a single MCP ``call_tool`` invocation.

    Written in a best-effort fashion by the transport wrapper — an audit
    failure must never take down the Agent execution. Rows are kept
    indefinitely for now; retention policy is a governance decision
    (Phase 2 §Knowledge Governance §cleanup).
    """
    __tablename__ = "mcp_tool_calls"

    mcp_server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_servers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    args: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # 'ok' | 'error'
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Soft context (nullable — ad-hoc admin tests carry none of these)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
