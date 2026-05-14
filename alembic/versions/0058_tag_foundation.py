"""Spec 25 Plan A — Tag-driven retrieval 数据底座

- knowledge_entries: 加 auto_tags / rejected_auto_tags JSONB
- chunks: 加 chunk_tags VARCHAR[] + GIN 索引（milvus array filter 对应的 PG 端镜像）
- 新表 tag_dictionary（KB 维度的 canonical + aliases 字典）+ unique(kb_id, lower(canonical))
- 新表 tag_dictionary_audit（字典操作审计 + 回填进度）
- 新表 kb_tag_settings（每 KB 一份的功能开关 + preset）

Revision ID: 0058
Revises: 0057
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── entries 增列 ─────────────────────────────────────────────
    op.add_column(
        "knowledge_entries",
        sa.Column("auto_tags", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "knowledge_entries",
        sa.Column("rejected_auto_tags", postgresql.JSONB, nullable=True),
    )

    # ── chunks.chunk_tags + GIN 索引 ─────────────────────────────
    op.add_column(
        "chunks",
        sa.Column("chunk_tags", postgresql.ARRAY(sa.String(64)), nullable=True),
    )
    op.create_index(
        "ix_chunks_chunk_tags_gin",
        "chunks", ["chunk_tags"],
        postgresql_using="gin",
    )

    # ── tag_dictionary ───────────────────────────────────────────
    op.create_table(
        "tag_dictionary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical", sa.String(64), nullable=False),
        sa.Column(
            "aliases", postgresql.JSONB,
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "usage_count", sa.Integer,
            nullable=False, server_default="0",
        ),
        sa.Column(
            "is_deprecated", sa.Boolean,
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("kb_id", "canonical", name="uq_tag_dict_kb_canonical"),
    )
    op.create_index("ix_tag_dictionary_kb", "tag_dictionary", ["kb_id"])
    # 大小写不敏感 lookup（PG 端 lower 查询走表达式索引）
    op.create_index(
        "ix_tag_dictionary_lower_canonical",
        "tag_dictionary",
        [sa.text("kb_id"), sa.text("lower(canonical)")],
    )

    # ── tag_dictionary_audit ────────────────────────────────────
    op.create_table(
        "tag_dictionary_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kb_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dict_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("op", sa.String(20), nullable=False),
        sa.Column("before", postgresql.JSONB, nullable=True),
        sa.Column("after", postgresql.JSONB, nullable=True),
        sa.Column("affected_entries", sa.Integer, nullable=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_tag_dict_audit_kb_created",
        "tag_dictionary_audit",
        ["kb_id", sa.text("created_at DESC")],
    )

    # ── kb_tag_settings ──────────────────────────────────────────
    op.create_table(
        "kb_tag_settings",
        sa.Column(
            "kb_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "preset", sa.String(20),
            nullable=False, server_default="balanced",
        ),
        sa.Column(
            "auto_tag_enabled", sa.Boolean,
            nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "auto_tag_provider", sa.String(20),
            nullable=False, server_default="hybrid",
        ),
        sa.Column(
            "auto_tag_llm_model_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_registry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "auto_tag_max_per_unit", sa.Integer,
            nullable=False, server_default="5",
        ),
        sa.Column(
            "auto_tag_confidence_threshold", sa.Float,
            nullable=False, server_default="0.6",
        ),
        sa.Column(
            "tag_filter_enabled", sa.Boolean,
            nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "tag_boost_weight", sa.Float,
            nullable=False, server_default="0.05",
        ),
        sa.Column(
            "tag_routing_enabled", sa.Boolean,
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("kb_tag_settings")
    op.drop_index("ix_tag_dict_audit_kb_created", table_name="tag_dictionary_audit")
    op.drop_table("tag_dictionary_audit")
    op.drop_index("ix_tag_dictionary_lower_canonical", table_name="tag_dictionary")
    op.drop_index("ix_tag_dictionary_kb", table_name="tag_dictionary")
    op.drop_table("tag_dictionary")
    op.drop_index("ix_chunks_chunk_tags_gin", table_name="chunks")
    op.drop_column("chunks", "chunk_tags")
    op.drop_column("knowledge_entries", "rejected_auto_tags")
    op.drop_column("knowledge_entries", "auto_tags")
