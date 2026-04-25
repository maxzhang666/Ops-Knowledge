"""knowledge review workflow (Plan 29 M1)

Spec `14-knowledge-governance.md §Cross-Cutting Knowledge review workflow`：
upload → pre-check → assign reviewer → approve → publish.

* ``knowledge_bases.review_required`` — opt-in per KB (default False to keep
  existing KBs' behavior unchanged).
* ``documents.review_status`` — None when KB has no review requirement;
  otherwise pending / approved / rejected.
* ``documents.reviewer_id`` — user who decided; ``reviewed_at`` + ``review_comment``
  are set on approve/reject.

Retrieval path filters non-approved chunks when KB.review_required is on.

Revision ID: 0038
Revises: 0037
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("review_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("review_comment", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_documents_kb_review_status",
        "documents",
        ["knowledge_base_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_kb_review_status", table_name="documents")
    op.drop_column("documents", "review_comment")
    op.drop_column("documents", "reviewed_at")
    op.drop_column("documents", "reviewer_id")
    op.drop_column("documents", "review_status")
    op.drop_column("knowledge_bases", "review_required")
