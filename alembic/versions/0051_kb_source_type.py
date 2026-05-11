"""knowledge_bases.source_type — KB 类型标识

Plan 40 M1.1 — 决定 IngestionPlugin。建库时选定，建库后不可改（unit 数据
形态决定，强制重建 KB）。

历史 KB 默认 source_type='file' 兼容现有文件型 KB。

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="file",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "source_type")
