"""retrieval_logs.results_json — Workbench history snapshot

Workbench M2.1 — store the actual hit list (chunk_id + content_preview +
score breakdown) per retrieval, so the history sidebar can replay a past
run as a snapshot rather than re-firing the pipeline (which costs API
calls and may produce different results when rerank/index changed).

JSONB column on the existing table — chosen over a child table because:
- One read = one row, no join
- Each retrieval has 5-20 chunks, payload stays small
- Trim chunk content to 500 chars in service.py before serialising

Revision ID: 0045
Revises: 0044
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column("results_json", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("retrieval_logs", "results_json")
