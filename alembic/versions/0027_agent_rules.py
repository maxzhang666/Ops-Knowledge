"""agent_rules — Orchestrator Agent 规则表 (Plan 31 N1)

每条规则一行，让运营可 SQL 查询命中排行 / 冷规则 / 平均延迟。

priority 用 DOUBLE PRECISION：拖拽重排在 (prev + next) / 2 插入中位数
即可，不需要多行原子更新，也不用唯一约束（N3 定时 rebalance 到整数）。

handler_config jsonb 承接各 handler_type 的特化参数（tool_name /
input_mapping / arg_template），不挤进 match_config。

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority", sa.Float(precision=53), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("match_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("handler_type", sa.String(20), nullable=False),
        sa.Column("handler_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "handler_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "on_handler_error",
            sa.String(20),
            nullable=False,
            server_default="use_default",
        ),
        sa.Column("hit_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    # Active-only covering index — 评估规则时几乎永远 is_active=true
    op.create_index(
        "idx_agent_rules_agent_priority",
        "agent_rules",
        ["agent_id", "priority"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_rules_agent_priority", table_name="agent_rules")
    op.drop_table("agent_rules")
