"""Golden Dataset evaluation (Plan 38 M1)

Spec phasing §Phase 3 "Batch evaluation system (Golden Dataset, automated
quality benchmarking)"。

3 张表：
  * golden_datasets         —— 数据集元数据（与 KB 关联）
  * golden_questions        —— 数据集内的问题 + 期望答案/chunk
  * golden_dataset_runs     —— 一次批量评估的运行记录（含聚合分）
  * golden_question_results —— 单题运行结果（per metric 分数）

Revision ID: 0043
Revises: 0042
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "golden_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_golden_datasets_kb", "golden_datasets", ["kb_id"])

    op.create_table(
        "golden_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column(
            "expected_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_golden_questions_dataset", "golden_questions", ["dataset_id"])

    op.create_table(
        "golden_dataset_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),  # {context_precision: avg, faithfulness: avg, ...}
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "triggered_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_golden_dataset_runs_dataset_started",
        "golden_dataset_runs",
        ["dataset_id", "started_at"],
    )

    op.create_table(
        "golden_question_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_dataset_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),  # {metric: score}
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_golden_question_results_run", "golden_question_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_golden_question_results_run", table_name="golden_question_results")
    op.drop_table("golden_question_results")
    op.drop_index("ix_golden_dataset_runs_dataset_started", table_name="golden_dataset_runs")
    op.drop_table("golden_dataset_runs")
    op.drop_index("ix_golden_questions_dataset", table_name="golden_questions")
    op.drop_table("golden_questions")
    op.drop_index("ix_golden_datasets_kb", table_name="golden_datasets")
    op.drop_table("golden_datasets")
