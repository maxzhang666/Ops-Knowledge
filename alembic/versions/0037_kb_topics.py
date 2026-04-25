"""kb_topics (Plan 26 T1 · Layer 5 Topic Distribution)

每 KB 的聚类话题结果 —— 由 ``topic_distribution_scan`` Celery 生成。
重跑时按 ``kb_id`` 整片覆盖，因此 ``cluster_id`` 仅作为同次扫描的稳定编号。

Revision ID: 0037
Revises: 0036
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("example_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("kb_id", "cluster_id", name="uq_kb_topics_kb_cluster"),
    )
    op.create_index("ix_kb_topics_kb_size", "kb_topics", ["kb_id", "size"])


def downgrade() -> None:
    op.drop_index("ix_kb_topics_kb_size", table_name="kb_topics")
    op.drop_table("kb_topics")
