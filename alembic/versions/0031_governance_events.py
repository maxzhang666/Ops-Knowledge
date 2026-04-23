"""chunk_usage_events + retrieval_no_result_events (Plan 32 M1.1)

Event log backing Phase 2 chunk dynamic scoring + knowledge gap detection.
Separate tables because cardinality + query pattern differ:
  - chunk_usage_events: many events per chunk, queried by chunk_id + time window
  - retrieval_no_result_events: per-query rows, queried by kb_id + time window,
    drives "knowledge gap" clustering (no existing chunk to FK against)

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # hit | adopted | feedback_positive | feedback_negative | feedback_reverse
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_chunk_events_chunk_time",
        "chunk_usage_events",
        ["chunk_id", "created_at"],
    )
    op.create_index(
        "idx_chunk_events_kb_type_time",
        "chunk_usage_events",
        ["kb_id", "event_type", "created_at"],
    )

    op.create_table(
        "retrieval_no_result_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_noresult_kb_time",
        "retrieval_no_result_events",
        ["kb_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_noresult_kb_time", table_name="retrieval_no_result_events")
    op.drop_table("retrieval_no_result_events")
    op.drop_index("idx_chunk_events_kb_type_time", table_name="chunk_usage_events")
    op.drop_index("idx_chunk_events_chunk_time", table_name="chunk_usage_events")
    op.drop_table("chunk_usage_events")
