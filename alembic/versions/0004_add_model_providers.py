"""add model_providers

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('model_providers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=True),
        sa.Column('api_key', sa.String(length=500), nullable=True),
        sa.Column('models_available', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('default_llm_model', sa.String(length=100), nullable=True),
        sa.Column('default_embedding_model', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_model_providers_type', 'model_providers', ['type'])
    op.create_index('ix_model_providers_is_active', 'model_providers', ['is_active'])
    op.create_index('ix_model_providers_created_by', 'model_providers', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_model_providers_created_by', table_name='model_providers')
    op.drop_index('ix_model_providers_is_active', table_name='model_providers')
    op.drop_index('ix_model_providers_type', table_name='model_providers')
    op.drop_table('model_providers')
