"""retrieval_recommendations (Plan 35 M3)

聚合输出：每 (kb_id, query_type) 当前最新建议；UNIQUE 保证按 KB+type
唯一。Celery rebuild 任务用 upsert 覆盖。

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_type", sa.String(length=32), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("kb_id", "query_type", name="uq_retrieval_reco_kb_type"),
    )


def downgrade() -> None:
    op.drop_table("retrieval_recommendations")
