"""agents.orchestrator_config JSONB — Orchestrator Agent 设置 (Plan 31 N1)

Agent 表仅有 ``retrieval_config``（KB-specific）。Orchestrator 需要独立的
配置承载（classifier + default_handler + trusted_metadata_paths +
diagnostic_mode_allowed_roles）；不复用 retrieval_config 避免语义污染。

对非 Orchestrator Agent 保持 NULL。

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "orchestrator_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "orchestrator_config")
