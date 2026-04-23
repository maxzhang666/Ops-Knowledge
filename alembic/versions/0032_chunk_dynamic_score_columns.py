"""Chunk denormalized dynamic-score columns (Plan 32 M1.1)

Queries for "top-adopted chunks" / "cold chunks" / dashboards shouldn't
scan the events table each time — we maintain per-chunk rollup counters
updated by Celery batch (see ``app.knowledge.governance.tasks``).

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("adopted_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chunks", sa.Column("feedback_positive", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chunks", sa.Column("feedback_negative", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chunks", sa.Column("quality_dynamic", sa.Float(), nullable=True))
    op.add_column("chunks", sa.Column("quality_composite", sa.Float(), nullable=True))
    op.add_column("chunks", sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chunks", sa.Column("last_adopted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "last_adopted_at")
    op.drop_column("chunks", "last_hit_at")
    op.drop_column("chunks", "quality_composite")
    op.drop_column("chunks", "quality_dynamic")
    op.drop_column("chunks", "feedback_negative")
    op.drop_column("chunks", "feedback_positive")
    op.drop_column("chunks", "adopted_count")
