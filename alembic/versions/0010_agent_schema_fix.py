"""Agent schema: model fields nullable, add workflow_id, add is_pinned to conversations

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agent: model_provider_id and model_name nullable
    op.alter_column('agents', 'model_provider_id', existing_type=postgresql.UUID(), nullable=True)
    op.alter_column('agents', 'model_name', existing_type=sa.String(100), nullable=True)

    # Agent: add workflow_id
    op.add_column('agents', sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=True))

    # Conversation: add is_pinned
    op.add_column('conversations', sa.Column('is_pinned', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('conversations', 'is_pinned')
    op.drop_column('agents', 'workflow_id')
    op.alter_column('agents', 'model_name', existing_type=sa.String(100), nullable=False)
    op.alter_column('agents', 'model_provider_id', existing_type=postgresql.UUID(), nullable=False)
