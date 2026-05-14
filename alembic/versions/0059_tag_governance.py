"""Spec 25 Plan E — 治理融合数据底座

新增：
- auto_tag_actions 审计表：记录 accept/reject 用户行为，供接受率统计
- retrieval_logs.tag_signals JSONB：每次检索的 tag 子系统使用信号
  ({tag_filter_used, routing_used, routed_tags, boost_weight, boosted_count})

Revision ID: 0059
Revises: 0058
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auto_tag_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_auto_tag_actions_kb", "auto_tag_actions", ["kb_id"])
    op.create_index("ix_auto_tag_actions_entry", "auto_tag_actions", ["entry_id"])
    op.create_index(
        "ix_auto_tag_actions_kb_action_created",
        "auto_tag_actions",
        ["kb_id", "action", sa.text("created_at DESC")],
    )

    op.add_column(
        "retrieval_logs",
        sa.Column("tag_signals", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("retrieval_logs", "tag_signals")
    op.drop_index("ix_auto_tag_actions_kb_action_created", table_name="auto_tag_actions")
    op.drop_index("ix_auto_tag_actions_entry", table_name="auto_tag_actions")
    op.drop_index("ix_auto_tag_actions_kb", table_name="auto_tag_actions")
    op.drop_table("auto_tag_actions")
