"""LangGraph checkpoint tables

Creates the 4 tables LangGraph's ``PostgresSaver`` expects:
``checkpoint_migrations``, ``checkpoints``, ``checkpoint_blobs``,
``checkpoint_writes``, plus the 3 thread_id indexes. DDL mirrors the
``MIGRATIONS`` constant in
``langgraph/checkpoint/postgres/base.py`` (langgraph==1.1.0) collapsed
into the final equivalent schema (we don't need to replay the
incremental ALTERs since we create fresh).

After creation, all rows 0..9 are inserted into ``checkpoint_migrations``
so that a subsequent ``PostgresSaver.setup()`` call (if any — Plan 29
forbids runtime setup but defence in depth is cheap) would see "already
at latest version" and skip.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Number of MIGRATIONS entries in langgraph==1.1.0's base.py. Pin this to the
# installed package; see Plan 29 §Dependencies.
_LANGGRAPH_MIGRATIONS_COUNT = 10


def upgrade() -> None:
    # Migration-tracking table used by LangGraph itself. We populate it below
    # so that PostgresSaver.setup() (if ever invoked) treats the schema as
    # up-to-date and skips all work.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_migrations (
            v INTEGER PRIMARY KEY
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint JSONB NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );
        """
    )

    # Note: `blob` column is nullable — langgraph applied an ALTER after the
    # initial create-table; we bake that in here.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            blob BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        );
        """
    )

    # Note: `task_path` column included from the start (langgraph added it
    # via a later ALTER — we bake it in).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            blob BYTEA NOT NULL,
            task_path TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        );
        """
    )

    # Thread-id indexes. langgraph's originals use CONCURRENTLY (non-blocking
    # on live tables); here the tables are brand-new and empty, so a plain
    # CREATE INDEX is equivalent and stays inside alembic's transaction.
    op.execute(
        "CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx "
        "ON checkpoints(thread_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx "
        "ON checkpoint_blobs(thread_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx "
        "ON checkpoint_writes(thread_id);"
    )

    # Mark all langgraph-internal migrations as applied.
    for v in range(_LANGGRAPH_MIGRATIONS_COUNT):
        op.execute(
            f"INSERT INTO checkpoint_migrations (v) VALUES ({v}) ON CONFLICT DO NOTHING;"
        )


def downgrade() -> None:
    # Order: tables with no FK → tables referenced. These four are
    # independent (no cross-FKs), so any order works; drop in reverse-create.
    op.execute("DROP TABLE IF EXISTS checkpoint_writes;")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs;")
    op.execute("DROP TABLE IF EXISTS checkpoints;")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations;")
