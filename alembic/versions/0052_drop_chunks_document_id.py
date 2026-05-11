"""drop chunks.document_id — Plan 40 M3 第二步部署收尾

迁移路径完成：
- 0050: 加 unit_type/unit_id（NULLABLE）+ backfill + alter document_id NULLABLE
- 0051: KB.source_type
- 0052（本迁移）: drop chunks.document_id 列 + alter unit_type/unit_id NOT NULL

⚠️ 生产部署前必须确认：
1. M2 双写监控 `chunks_dual_write_diff_count` 持续 = 0 至少一个 release cycle
2. grep 全 codebase 无 chunks.document_id 引用：
   ``grep -rn 'Chunk\\.document_id\\|chunks\\.document_id' app/``

回滚高代价：downgrade 需重新加列 + 从 unit_id 反向 backfill + 长锁。生产推荐
forward-fix 而非 rollback。

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. drop document_id 索引 + 列
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_column("chunks", "document_id")
    # 2. unit_type / unit_id 改 NOT NULL（M2 双写期所有行都已 backfill）
    op.alter_column("chunks", "unit_type", nullable=False)
    op.alter_column("chunks", "unit_id", nullable=False)


def downgrade() -> None:
    # 反向迁移代价高：重建列 + 反向 backfill + 索引。
    # 实操不推荐 — 优先 forward-fix。这里保留以便紧急 staging 回滚。
    op.alter_column("chunks", "unit_id", nullable=True)
    op.alter_column("chunks", "unit_type", nullable=True)
    op.add_column(
        "chunks",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "UPDATE chunks SET document_id=unit_id WHERE unit_type='document'"
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    # 注意：不加回 FK constraint，因为 docs 行可能已删除
