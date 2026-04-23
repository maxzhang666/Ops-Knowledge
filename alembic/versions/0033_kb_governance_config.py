"""knowledge_bases.governance_config JSONB (Plan 32 M1.1 / M3)

Per-KB policy knob. Schema (see ``app.knowledge.governance.schemas``):
  {
    "expiration_threshold_days": 90,
    "auto_archive_idle_days": 30
  }
NULL = use system defaults.

Revision ID: 0033
Revises: 0032
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "governance_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "governance_config")
