"""agent_rule_versions — 规则版本快照（Plan 31 N3.1）

每次规则编辑保存一份 snapshot；运营可按历史回滚。表结构对应
AgentRule 的关键业务字段，不带 hit_count / last_hit_at 这类运行时
统计（snapshot 是"配置"层面，不是"运行"层面）。

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_rules.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Float(precision=53), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("match_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("handler_type", sa.String(20), nullable=False),
        sa.Column("handler_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("handler_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("on_handler_error", sa.String(20), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("rule_id", "version", name="uq_agent_rule_version"),
    )


def downgrade() -> None:
    op.drop_table("agent_rule_versions")
