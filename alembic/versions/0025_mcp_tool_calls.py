"""mcp_tool_calls — per-invocation audit log (Plan 30 M3).

Every MCP ``call_tool`` lands here so admins can see what the Agents
actually asked for, with what args, and what came back. ``args`` /
``result`` are JSONB — MCP tool payloads are arbitrary JSON.

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mcp_server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),  # 'ok' | 'error'
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        # Context (soft FKs — callers may not always have these)
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column(
            "called_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_mcp_tool_calls_server_time",
        "mcp_tool_calls",
        ["mcp_server_id", "called_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_mcp_tool_calls_server_time", table_name="mcp_tool_calls")
    op.drop_table("mcp_tool_calls")
