"""Conversation.status + closed_at for soft-archive + TTL

Plan 29 Open Q resolution: add ``status`` (active / archived) and
``closed_at`` to ``conversations`` so the checkpoint TTL task can use a
precise close timestamp instead of the ``updated_at`` proxy, and so
"delete" becomes soft-archive (7-day grace before Celery hard-deletes).

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # TTL task scans archived + closed_at<cutoff; composite index keeps the
    # predicate index-only on even very large conversation tables.
    op.create_index(
        "ix_conversations_status_closed_at",
        "conversations",
        ["status", "closed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_status_closed_at", table_name="conversations")
    op.drop_column("conversations", "closed_at")
    op.drop_column("conversations", "status")
