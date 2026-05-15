"""entry last_user_edited_at for user-action-only timestamps

产品视角下"操作记录"应只反映用户主动编辑的时间，不被后续 embedding /
review / lifecycle 等系统 UPDATE 污染（这些 UPDATE 会通过 onupdate=now()
重写 updated_at，让"昨天编辑"显示成"几秒前"）。

新字段仅由 plugin.create_unit / update_unit 在检测到用户可见字段
（title / content / tags / folder）变化时显式 set；其他路径不动它。

Backfill 选 created_at 而不是 updated_at —— updated_at 可能已被
embedding/review 流程污染，回填它会让历史条目都"看起来刚编辑过"，反向
踩本次要修的 bug；created_at 是最保守的下限。

Revision ID: 0061
Revises: 0060
"""
from __future__ import annotations

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_entries "
        "ADD COLUMN last_user_edited_at TIMESTAMPTZ"
    )
    # Backfill 用 created_at（保守下限），未来用户编辑会按真实时间更新
    op.execute(
        "UPDATE knowledge_entries "
        "SET last_user_edited_at = created_at "
        "WHERE last_user_edited_at IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_entries DROP COLUMN IF EXISTS last_user_edited_at"
    )
