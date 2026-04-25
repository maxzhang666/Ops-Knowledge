"""retrieval_logs (Plan 35 M2 · auto-tuning data backbone)

每次检索一行：用于按 (kb, query_type) 聚合 hit/adopted 信号，反推
最优 hybrid 权重与 top_k。

字段：
  * kb_id          —— 检索目标 KB
  * query          —— 原始 query (≤500 字符)
  * query_type     —— QueryClassifier 输出
  * top_k          —— 调用配置
  * result_count   —— 返回结果数（0 = 无结果，与 RetrievalNoResultEvent 重叠）
  * created_at

为聚合性能加 (kb_id, query_type, created_at) 复合索引。

Revision ID: 0041
Revises: 0040
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("query_type", sa.String(length=32), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_retrieval_logs_kb_type_created",
        "retrieval_logs",
        ["kb_id", "query_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_logs_kb_type_created", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")
