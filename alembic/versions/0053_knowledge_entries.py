"""knowledge_entries — 条目型 KB 独占表（Plan 41 M1.1）

每条 entry 是用户在线编辑的短词条（FAQ / SOP / 客服话术）。
- 不挂 folder（条目型无目录树）
- 不挂 file_path（无对象存储文件）
- ≤ 1500 token 时一条一 chunk（不切片）；超长走通用 markdown 切片
- review_required=True 时全套 review 字段镜像 documents（Plan 29 兼容）

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "knowledge_base_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_archived", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        # Plan 32 M3 lifecycle 两阶段（与 documents 对齐）
        sa.Column(
            "is_stale", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
        # Plan 29 review fields（镜像 documents）
        sa.Column("review_status", sa.String(20), nullable=True),
        sa.Column(
            "reviewer_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        # Plan 39 通知去重锚点
        sa.Column(
            "last_pending_started_at",
            sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_knowledge_entries_kb",
        "knowledge_entries", ["knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_entries_kb_review",
        "knowledge_entries", ["knowledge_base_id", "review_status"],
    )
    op.create_index(
        "ix_knowledge_entries_kb_archived",
        "knowledge_entries", ["knowledge_base_id", "is_archived"],
    )
    op.create_index(
        "ix_knowledge_entries_kb_stale",
        "knowledge_entries", ["knowledge_base_id", "is_stale"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_entries_kb_stale", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_kb_archived", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_kb_review", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_kb", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
