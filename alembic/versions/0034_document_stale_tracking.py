"""documents.is_stale + stale_since (Plan 32 M3 lifecycle)

Spec `14-knowledge-governance.md §Lifecycle`: the daily `document_lifecycle`
Celery task marks documents whose `updated_at` crosses the KB's expiration
threshold (or whose rolling 7d hit count drops > 70%) as stale. Stale-since
timestamp drives:

  * "auto-archive after N idle days" — compare `now - stale_since > idle_days`.
  * Idempotent notifications — only notify on the transition `False → True`.

Revision ID: 0034
Revises: 0033
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "documents",
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_documents_kb_is_stale",
        "documents",
        ["knowledge_base_id", "is_stale"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_kb_is_stale", table_name="documents")
    op.drop_column("documents", "stale_since")
    op.drop_column("documents", "is_stale")
