"""retrieval_logs.is_test — Workbench 测试标志

M6.5 — 区分 Workbench / Quick QA / Golden 评估等"测试性"检索与真实
chat / agent / workflow 检索。is_test=True 的 log 仍然写入（让 Workbench
历史侧栏可见），但治理统计 / Plan 35 推荐查询时 WHERE is_test=False，
避免实验调参污染真实使用画像。

Revision ID: 0046
Revises: 0045
Create Date: 2026-04-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # 已有行（pre-0046 没有 is_test 信号）默认按 False 处理 —— 这些数据
    # 已被治理消费过，重写历史不必要。
    op.create_index(
        "ix_retrieval_logs_kb_is_test_created",
        "retrieval_logs",
        ["kb_id", "is_test", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_logs_kb_is_test_created", table_name="retrieval_logs")
    op.drop_column("retrieval_logs", "is_test")
