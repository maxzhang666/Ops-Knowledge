"""add agents table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('avatar', sa.String(length=500), nullable=True),
        sa.Column('agent_type', sa.String(length=20), nullable=False, server_default='simple'),
        sa.Column('knowledge_base_ids', postgresql.JSONB(), nullable=True),
        sa.Column('folder_ids', postgresql.JSONB(), nullable=True),
        sa.Column('model_provider_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('retrieval_config', postgresql.JSONB(), nullable=True),
        sa.Column('welcome_message', sa.Text(), nullable=True),
        sa.Column('show_thinking', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('thinking_detail', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('no_result_mode', sa.String(length=20), nullable=False, server_default='honest'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['model_provider_id'], ['model_providers.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    op.create_index('ix_agents_created_by', 'agents', ['created_by'])
    op.create_index('ix_agents_is_active', 'agents', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_agents_is_active', table_name='agents')
    op.drop_index('ix_agents_created_by', table_name='agents')
    op.drop_table('agents')
