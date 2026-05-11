"""knowledge_entries.status — 条目处理状态

Plan 41 — 让用户看到条目从创建到可检索的状态变化：
- pending: 刚创建，chunks 尚未生成
- processing: chunks 已写入，embedding 进行中
- completed: 全部 chunks vector_id 已落值，可检索
- error: embedding 失败

create_entry 默认 'processing'（chunks 同步生成 + 异步 embed 立即触发，几乎不停留 pending）；
embed task 完成后 update completed；失败 update error。

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_entries",
        sa.Column(
            "status", sa.String(20),
            nullable=False, server_default="pending",
        ),
    )
    op.add_column(
        "knowledge_entries",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_knowledge_entries_kb_status",
        "knowledge_entries", ["knowledge_base_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_entries_kb_status", table_name="knowledge_entries")
    op.drop_column("knowledge_entries", "error_message")
    op.drop_column("knowledge_entries", "status")
