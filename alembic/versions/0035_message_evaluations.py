"""message_evaluations (Plan 25 · Layer 3-4 eval)

Spec `14-knowledge-governance.md §Layer 3/4`：per-message quality scores
produced by LLM-as-judge pipeline. One row per (message_id, metric) so
each metric can evolve independently.

Columns:
  * metric           — context_precision / faithfulness / answer_relevancy / hallucination / citation_accuracy
  * score            — 0..1 float
  * rationale        — LLM 判断过程简述（debug / 审计用）
  * judge_model      — 记录使用的 judge 模型名，便于指标可比性追溯
  * sample_count     — 有些指标聚合多个 chunk 的子分（如 context_precision 是每 chunk 相关性平均），这里记采样数
  * evaluated_at

UNIQUE (message_id, metric) — 重跑覆盖上次结果。

Revision ID: 0035
Revises: 0034
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("judge_model", sa.String(length=120), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("message_id", "metric", name="uq_message_evaluations_msg_metric"),
    )
    op.create_index(
        "ix_message_evaluations_kb_metric_evaluated",
        "message_evaluations",
        ["kb_id", "metric", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_message_evaluations_kb_metric_evaluated",
        table_name="message_evaluations",
    )
    op.drop_table("message_evaluations")
