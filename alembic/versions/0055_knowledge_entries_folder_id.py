"""knowledge_entries.folder_id — 条目目录化（Plan 41）

让条目型 KB 复用 folders 表（用户反馈：扁平化对大知识量维护不友好）。
folder_id 可空（默认根目录），ON DELETE SET NULL（删除文件夹时条目移到根）。

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_entries",
        sa.Column(
            "folder_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_entries_folder",
        "knowledge_entries", ["folder_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_entries_folder", table_name="knowledge_entries")
    op.drop_column("knowledge_entries", "folder_id")
