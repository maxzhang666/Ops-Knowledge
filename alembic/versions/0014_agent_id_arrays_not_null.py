"""agents.knowledge_base_ids/folder_ids: NOT NULL with default '[]'

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fill existing NULLs so the NOT NULL constraint can be applied
    op.execute(
        "UPDATE agents SET knowledge_base_ids = '[]'::jsonb "
        "WHERE knowledge_base_ids IS NULL"
    )
    op.execute(
        "UPDATE agents SET folder_ids = '[]'::jsonb "
        "WHERE folder_ids IS NULL"
    )

    op.alter_column(
        'agents', 'knowledge_base_ids',
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    op.alter_column(
        'agents', 'folder_ids',
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        'agents', 'knowledge_base_ids',
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        'agents', 'folder_ids',
        nullable=True,
        server_default=None,
    )
