"""workflows.owner_agent_id — Workflow ↔ Agent ownership (Plan 31 N2.9)

Orchestrator Agent 拥有 N 个 Workflow（每个 Workflow 一个独立 SOP 画布）;
Workflow Agent 的 1:1 绑定也走这个字段（N=1 特例）。NULL 保留给模板 /
历史独立 Workflow。

ON DELETE CASCADE：删除 Agent 时连带删掉其名下 Workflow —— 业务上
Workflow 是 Agent 的子资源，离开 Agent 无意义。

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column(
            "owner_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_workflows_owner_agent",
        "workflows",
        ["owner_agent_id"],
        postgresql_where=sa.text("owner_agent_id IS NOT NULL"),
    )

    # Backfill: each Workflow Agent's Agent.workflow_id points at its workflow;
    # mirror that as owner_agent_id on the workflow side so the reverse
    # relation is consistent from day one.
    op.execute(
        """
        UPDATE workflows w
        SET owner_agent_id = a.id
        FROM agents a
        WHERE a.workflow_id = w.id
          AND a.agent_type = 'workflow'
          AND w.owner_agent_id IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_workflows_owner_agent", table_name="workflows")
    op.drop_column("workflows", "owner_agent_id")
