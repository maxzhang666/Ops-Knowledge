"""add chunks table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('folder_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('parent_chunk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('level', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('vector_id', sa.String(length=100), nullable=True),
        sa.Column('is_manually_edited', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('edit_history', postgresql.JSONB(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_chunk_id'], ['chunks.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_chunks_document_id', 'chunks', ['document_id'])
    op.create_index('ix_chunks_knowledge_base_id', 'chunks', ['knowledge_base_id'])
    op.create_index('ix_chunks_folder_id', 'chunks', ['folder_id'])
    op.create_index('ix_chunks_vector_id', 'chunks', ['vector_id'])


def downgrade() -> None:
    op.drop_index('ix_chunks_vector_id', table_name='chunks')
    op.drop_index('ix_chunks_folder_id', table_name='chunks')
    op.drop_index('ix_chunks_knowledge_base_id', table_name='chunks')
    op.drop_index('ix_chunks_document_id', table_name='chunks')
    op.drop_table('chunks')
