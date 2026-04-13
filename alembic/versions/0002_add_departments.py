"""add departments

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE department_role AS ENUM ('dept_admin', 'editor', 'viewer'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table('departments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('parent_department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_department_id'], ['departments.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_departments_parent_department_id', 'departments', ['parent_department_id'])

    op.create_table('user_departments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Enum('dept_admin', 'editor', 'viewer', name='department_role'), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'department_id'),
    )
    op.create_index('ix_user_departments_user_id', 'user_departments', ['user_id'])
    op.create_index('ix_user_departments_department_id', 'user_departments', ['department_id'])

    op.create_table('department_resources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('access_level', sa.String(length=20), nullable=False),
        sa.Column('shared_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by'], ['users.id']),
        sa.UniqueConstraint('department_id', 'resource_type', 'resource_id'),
    )
    op.create_index('ix_department_resources_department_id', 'department_resources', ['department_id'])


def downgrade() -> None:
    op.drop_index('ix_department_resources_department_id', table_name='department_resources')
    op.drop_table('department_resources')
    op.drop_index('ix_user_departments_department_id', table_name='user_departments')
    op.drop_index('ix_user_departments_user_id', table_name='user_departments')
    op.drop_table('user_departments')
    op.drop_index('ix_departments_parent_department_id', table_name='departments')
    op.drop_table('departments')
    op.execute("DROP TYPE department_role")
