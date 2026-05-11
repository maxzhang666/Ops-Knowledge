"""knowledge_bases.health_score / health_score_updated_at — KB 健康分缓存

列表 API 直接 SELECT，避免 N+1 调用 GovernanceService.compute_health。
写回触发点：每日 governance_alert_publish_daily 任务 + 详情页
GET /knowledge/{kb_id}/governance（顺手刷新）。

NULL = 从未计算过（新建 KB 在首次 daily / 首次详情页访问之前），
前端渲染占位 "—"。

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("health_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("health_score_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "health_score_updated_at")
    op.drop_column("knowledge_bases", "health_score")
