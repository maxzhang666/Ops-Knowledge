"""add knowledge_bases, folders, documents

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up leftover enums from any previous failed run
    op.execute("DROP TYPE IF EXISTS kb_status")
    op.execute("DROP TYPE IF EXISTS document_status")

    # -- knowledge_bases --
    op.create_table('knowledge_bases',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('embedding_provider_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('embedding_model_name', sa.String(length=100), nullable=True),
        sa.Column('chunking_config', postgresql.JSONB(), nullable=True),
        sa.Column('retrieval_config', postgresql.JSONB(), nullable=True),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('active', 'indexing', 'error', 'deleting', name='kb_status'), nullable=False, server_default='active'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['embedding_provider_id'], ['model_providers.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    op.create_index('ix_knowledge_bases_status', 'knowledge_bases', ['status'])
    op.create_index('ix_knowledge_bases_created_by', 'knowledge_bases', ['created_by'])

    # -- folders --
    op.create_table('folders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('parent_folder_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_folder_id'], ['folders.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_folders_knowledge_base_id', 'folders', ['knowledge_base_id'])
    op.create_index('ix_folders_parent_folder_id', 'folders', ['parent_folder_id'])

    # -- documents --
    op.create_table('documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('folder_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'error', name='document_status'), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('processing_progress', postgresql.JSONB(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    op.create_index('ix_documents_knowledge_base_id', 'documents', ['knowledge_base_id'])
    op.create_index('ix_documents_folder_id', 'documents', ['folder_id'])
    op.create_index('ix_documents_file_hash', 'documents', ['file_hash'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_created_by', 'documents', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_documents_created_by', table_name='documents')
    op.drop_index('ix_documents_status', table_name='documents')
    op.drop_index('ix_documents_file_hash', table_name='documents')
    op.drop_index('ix_documents_folder_id', table_name='documents')
    op.drop_index('ix_documents_knowledge_base_id', table_name='documents')
    op.drop_table('documents')

    op.drop_index('ix_folders_parent_folder_id', table_name='folders')
    op.drop_index('ix_folders_knowledge_base_id', table_name='folders')
    op.drop_table('folders')

    op.drop_index('ix_knowledge_bases_created_by', table_name='knowledge_bases')
    op.drop_index('ix_knowledge_bases_status', table_name='knowledge_bases')
    op.drop_table('knowledge_bases')

    sa.Enum(name='document_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='kb_status').drop(op.get_bind(), checkfirst=True)
