"""model_registry.vector_dim — 记录 embedding 模型的向量维度

用途：Milvus 治理面板对账时，比对 KB 当前 embedding model 的维度
与 milvus collection 实际维度。避免每次 dim_probe 调一次 embedding
API。embed task 第一次跑时填充该字段。

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_registry",
        sa.Column("vector_dim", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_registry", "vector_dim")
