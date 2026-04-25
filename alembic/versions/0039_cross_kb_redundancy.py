"""chunk_cross_kb_redundancy_pairs (Plan 31 M1 · cross-KB governance)

Spec `14-knowledge-governance.md §Cross-Knowledge-Base Governance` →
duplication detection across KBs。

Per-KB redundancy 已有 ``chunk_redundancy_pairs``；这张表记录跨 KB 对：
``kb_a < kb_b``（确保有序避免双向重复行）+ chunk_a / chunk_b。

Revision ID: 0039
Revises: 0038
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_cross_kb_redundancy_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kb_b_id",
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
            name="uq_cross_kb_redundancy_ordered_pair",
        ),
        sa.CheckConstraint(
            "kb_a_id < kb_b_id",
            name="ck_cross_kb_redundancy_kb_ordering",
        ),
    )
    op.create_index(
        "ix_cross_kb_redundancy_sim",
        "chunk_cross_kb_redundancy_pairs",
        ["similarity"],
    )
    op.create_index(
        "ix_cross_kb_redundancy_kb_pair",
        "chunk_cross_kb_redundancy_pairs",
        ["kb_a_id", "kb_b_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cross_kb_redundancy_kb_pair", table_name="chunk_cross_kb_redundancy_pairs")
    op.drop_index("ix_cross_kb_redundancy_sim", table_name="chunk_cross_kb_redundancy_pairs")
    op.drop_table("chunk_cross_kb_redundancy_pairs")
