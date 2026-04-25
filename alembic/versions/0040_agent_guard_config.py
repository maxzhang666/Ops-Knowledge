"""agents.guard_config (Plan 33 M2 · Prompt injection defense)

Per-agent guardrail policy:
  {
    "mode": "off" | "log" | "block",
    "block_threshold": 0.7,
    "log_threshold": 0.4
  }
NULL → off (legacy default).

Revision ID: 0040
Revises: 0039
Create Date: 2026-04-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "guard_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "guard_config")
