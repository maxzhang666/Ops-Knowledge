"""Drop conversation.status + closed_at

Reverts migration 0020. Product decision: no soft-delete / TTL layer on
conversations. ``delete_conversation`` is hard-delete (with synchronous
checkpoint cleanup in the same transaction).

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_conversations_status_closed_at", table_name="conversations")
    op.drop_column("conversations", "closed_at")
    op.drop_column("conversations", "status")


def downgrade() -> None:
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
    op.create_index(
        "ix_conversations_status_closed_at",
        "conversations",
        ["status", "closed_at"],
    )
