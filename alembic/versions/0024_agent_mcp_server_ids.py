"""Agent.mcp_server_ids — binds an Agent to MCP servers (Plan 30 M2).

JSONB list of server UUIDs (same shape as ``knowledge_base_ids``).
Default ``[]`` so existing Agents remain valid.

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "mcp_server_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "mcp_server_ids")
