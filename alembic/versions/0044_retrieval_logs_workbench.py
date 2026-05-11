"""retrieval_logs — workbench fields (Retrieval Workbench M1.1)

Plan 35 wrote retrieval_logs with the bare minimum needed for auto-tuning
aggregations. The Retrieval Workbench (Phase 2 follow-up) needs to replay
each test run with full parameter context, so add:

* params_json   — full request payload (top_k_used, weights, threshold,
                  rerank, folder_ids, embedding model id, etc.) so the UI
                  can re-run and diff
* latency_ms    — total wall-clock time including rewrite + retrieve +
                  rerank + post-filter (the existing log row had no timing)
* created_by    — auth user id (nullable; backfill NULL for legacy rows
                  pre-workbench). Lets the UI show "my history".

Revision ID: 0044
Revises: 0043
Create Date: 2026-04-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column("params_json", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "retrieval_logs",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Index for "show my history sorted by recency" queries.
    op.create_index(
        "ix_retrieval_logs_user_created",
        "retrieval_logs",
        ["created_by", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_logs_user_created", table_name="retrieval_logs")
    op.drop_column("retrieval_logs", "created_by")
    op.drop_column("retrieval_logs", "latency_ms")
    op.drop_column("retrieval_logs", "params_json")
