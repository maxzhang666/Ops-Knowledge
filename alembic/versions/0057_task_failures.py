"""task_failures — Celery 失败任务持久化日志

捕获 task_failure / task_unknown signal，覆盖：FAILURE (异常 retries 用尽)
/ UNREGISTERED (worker 未注册 task name，否则被 celery 静默 discard) /
TIMEOUT (SoftTimeLimitExceeded)。daily cleanup 90 天后 hard delete。

详见 spec 19 §16 Task Failure Tracking。

Revision ID: 0057
Revises: 0056
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("args_json", postgresql.JSONB, nullable=True),
        sa.Column("kwargs_json", postgresql.JSONB, nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("exception", sa.Text, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("retries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("retried_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_task_failures_task_id", "task_failures", ["task_id"],
    )
    op.create_index(
        "ix_task_failures_resolved_at", "task_failures", ["resolved_at"],
    )
    # 列表主路径：按状态+时间倒序
    op.create_index(
        "ix_task_failures_state_failed",
        "task_failures", ["state", sa.text("failed_at DESC")],
    )
    # 按 task 类型聚合
    op.create_index(
        "ix_task_failures_task_name_failed",
        "task_failures", ["task_name", sa.text("failed_at DESC")],
    )
    # 按 KB 看相关失败
    op.create_index(
        "ix_task_failures_kb_failed",
        "task_failures", ["kb_id", sa.text("failed_at DESC")],
    )
    # Badge pendingCount 热路径：最近 24h 未 resolve 部分索引
    op.create_index(
        "ix_task_failures_unresolved",
        "task_failures", [sa.text("failed_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_task_failures_unresolved", table_name="task_failures")
    op.drop_index("ix_task_failures_kb_failed", table_name="task_failures")
    op.drop_index("ix_task_failures_task_name_failed", table_name="task_failures")
    op.drop_index("ix_task_failures_state_failed", table_name="task_failures")
    op.drop_index("ix_task_failures_resolved_at", table_name="task_failures")
    op.drop_index("ix_task_failures_task_id", table_name="task_failures")
    op.drop_table("task_failures")
