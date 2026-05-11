"""chunks.review_excluded — 审核期内容隔离派生列

Plan 39 M1.1 — 让 pending 状态的 unit 的所有 chunks 不参与召回 / 命中统计 / 治理动态分。
由 ReviewService 维护：
- chunks 写入时根据当前 unit.review_status 设置（pending / rejected → true）
- 审核 approve 时同步 UPDATE chunks SET review_excluded=false WHERE unit_type=? AND unit_id=?
- 审核 reject 后内容永远不进召回（保持 review_excluded=true）

历史 chunks 默认 review_excluded=false（保留历史召回行为）。

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "review_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # 检索 / 治理常用过滤组合：(kb_id, review_excluded)
    op.create_index(
        "ix_chunks_kb_review_excluded",
        "chunks",
        ["knowledge_base_id", "review_excluded"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_kb_review_excluded", table_name="chunks")
    op.drop_column("chunks", "review_excluded")
