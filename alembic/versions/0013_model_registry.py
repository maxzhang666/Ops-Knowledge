"""add model_registry table, FK columns on agents and knowledge_bases

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. model_registry table
    op.create_table('model_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_id', sa.String(length=200), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('model_type', sa.String(length=20), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['provider_id'], ['model_providers.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_id', 'model_id', name='uq_provider_model'),
    )
    op.create_index('ix_model_registry_provider_id', 'model_registry', ['provider_id'])

    # 2. agents.model_id -> model_registry FK (nullable, coexists with old columns)
    op.add_column('agents', sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_agents_model_id', 'agents', 'model_registry',
        ['model_id'], ['id'], ondelete='SET NULL',
    )

    # 3. knowledge_bases.embedding_model_id -> model_registry FK (nullable, coexists with old columns)
    op.add_column('knowledge_bases', sa.Column('embedding_model_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_kb_embedding_model_id', 'knowledge_bases', 'model_registry',
        ['embedding_model_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_kb_embedding_model_id', 'knowledge_bases', type_='foreignkey')
    op.drop_column('knowledge_bases', 'embedding_model_id')

    op.drop_constraint('fk_agents_model_id', 'agents', type_='foreignkey')
    op.drop_column('agents', 'model_id')

    op.drop_index('ix_model_registry_provider_id', table_name='model_registry')
    op.drop_table('model_registry')
