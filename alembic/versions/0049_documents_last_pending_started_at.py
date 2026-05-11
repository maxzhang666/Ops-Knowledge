"""documents.last_pending_started_at — 审核通知去重锚点

Plan 39 M2 — 同一 (unit_type, unit_id) 在 pending 状态期间的多次编辑提交
仅触发一条 review_pending 通知。状态切换到 approved/rejected 后再次进入
pending 才重置去重，触发新通知。

实现：should_notify_review_pending() 查 notifications.created_at
> unit.last_pending_started_at，存在即跳过；不存在才发。

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "last_pending_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "last_pending_started_at")
