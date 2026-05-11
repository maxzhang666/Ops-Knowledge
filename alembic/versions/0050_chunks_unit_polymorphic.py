"""chunks 多态 FK：unit_type + unit_id（替代 document_id 单向关联）

Plan 40 M1.1 — 两步部署的第一步：
- 加 unit_type VARCHAR 20 + unit_id UUID（NULLABLE）
- document_id 改 NULLABLE（条目型 / 代码型 / 外部同步等非 document unit 的 chunks 可不填）
- batched UPDATE backfill 已有 chunks 为 unit_type='document', unit_id=document_id
- 新增 (unit_type, unit_id) 索引

第二步部署（Plan 40 M3）会 DROP document_id 列；M1 → M3 之间双写 + 切读 + 监控。

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("unit_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("chunks", "document_id", nullable=True)

    # Backfill：所有现有 chunks 都来自 documents。
    # alembic 默认单事务模式不能用 DO + COMMIT 分批；当前项目 chunks 量级
    # 在 alembic upgrade 窗口内单条 UPDATE 可接受。
    # 生产超大表（千万级）应：禁用 alembic transaction → 手动 batched UPDATE
    # （SKIP LOCKED + COMMIT per batch）→ 详见 Plan 40 M1.1 实施说明。
    op.execute(
        "UPDATE chunks SET unit_type='document', unit_id=document_id "
        "WHERE document_id IS NOT NULL AND unit_type IS NULL"
    )

    op.create_index(
        "ix_chunks_unit_type_unit_id",
        "chunks",
        ["unit_type", "unit_id"],
    )


def downgrade() -> None:
    # 回滚仅在 M1 阶段安全（生产无非 document 的 chunks）。
    # 如果生产已经写入 unit_type != 'document' 的 chunks（Plan 41 上线后），
    # 必须先清理：DELETE FROM chunks WHERE unit_type != 'document'。
    op.drop_index("ix_chunks_unit_type_unit_id", table_name="chunks")
    op.drop_column("chunks", "unit_id")
    op.drop_column("chunks", "unit_type")
    op.alter_column("chunks", "document_id", nullable=False)
