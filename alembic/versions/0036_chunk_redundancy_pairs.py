"""chunk_redundancy_pairs (Plan 26 M1 · Layer 5 redundancy)

Spec `14-knowledge-governance.md §Layer 5 Redundancy`：存储同 KB 内
向量余弦相似度超过阈值的 chunk 对。由 ``redundancy_scan`` daily
Celery 扫描产出；治理服务读该表生成 redundancy alert。

UNIQUE (chunk_a, chunk_b) with ordering chunk_a < chunk_b 防止重复写入。

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_redundancy_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "chunk_a_id", "chunk_b_id",
            name="uq_chunk_redundancy_ordered_pair",
        ),
        sa.CheckConstraint(
            "chunk_a_id < chunk_b_id",
            name="ck_chunk_redundancy_ordering",
        ),
    )
    op.create_index(
        "ix_chunk_redundancy_kb_sim",
        "chunk_redundancy_pairs",
        ["kb_id", "similarity"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_redundancy_kb_sim", table_name="chunk_redundancy_pairs")
    op.drop_table("chunk_redundancy_pairs")
