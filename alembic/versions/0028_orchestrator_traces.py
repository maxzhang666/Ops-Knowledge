"""orchestrator_traces — 每次路由决策写一行 (Plan 31 N1, M1)

含 user_id + metadata_snapshot — 运营按用户维度统计、debug "为什么
vip 规则没命中" 必需。

fallback_next 语义下一次路由可能写两行（第一个失败记一行、最终成功
再记一行；共享 conversation_id + user_message 区分）。

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "matched_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_type_used", sa.String(20), nullable=True),
        sa.Column("match_latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_classifier_category", sa.String(100), nullable=True),
        sa.Column("llm_classifier_confidence", sa.Float(), nullable=True),
        sa.Column(
            "llm_classifier_cached",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("handler_type", sa.String(20), nullable=True),
        sa.Column("handler_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("handler_latency_ms", sa.Integer(), nullable=True),
        sa.Column("handler_status", sa.String(30), nullable=True),
        sa.Column("tried_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ab_group", sa.String(4), nullable=True),  # N3
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_orch_traces_agent_created",
        "orchestrator_traces",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_orch_traces_rule",
        "orchestrator_traces",
        ["matched_rule_id"],
        postgresql_where=sa.text("matched_rule_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_orch_traces_rule", table_name="orchestrator_traces")
    op.drop_index("idx_orch_traces_agent_created", table_name="orchestrator_traces")
    op.drop_table("orchestrator_traces")
