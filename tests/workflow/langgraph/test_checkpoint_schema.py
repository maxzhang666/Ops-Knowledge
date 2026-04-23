"""Phase 1 — alembic migration 0019 sanity checks.

These are **static** checks (no DB connection):
 - Migration file exists and is loadable by alembic's script directory.
 - `upgrade()` / `downgrade()` are callable (signature sanity).
 - DDL contains the expected table names and key columns so it can't
   silently regress.

Full schema-on-live-DB verification is deferred to Phase 2 (when we add
an alembic-aware conftest). Until then, trust `make migrate` + manual
`psql \\d` spot-check.
"""
from __future__ import annotations

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "0019_langgraph_checkpoint_tables.py"
)


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file(), f"migration not found: {MIGRATION_PATH}"


def test_migration_declares_correct_revision_and_parent() -> None:
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "0019"' in src
    assert 'down_revision: Union[str, None] = "0018"' in src


def test_migration_creates_all_four_tables() -> None:
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    for table in (
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in src, (
            f"migration missing CREATE TABLE for {table}"
        )


def test_migration_creates_three_indexes() -> None:
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    for idx in (
        "checkpoints_thread_id_idx",
        "checkpoint_blobs_thread_id_idx",
        "checkpoint_writes_thread_id_idx",
    ):
        assert idx in src, f"migration missing index {idx}"


def test_migration_has_downgrade_dropping_all_tables() -> None:
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    for table in (
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    ):
        assert f"DROP TABLE IF EXISTS {table}" in src, (
            f"downgrade missing DROP TABLE for {table}"
        )


def test_checkpoint_writes_includes_task_path() -> None:
    """`task_path` was added by a later LangGraph internal migration; our
    0019 must bake it in at create time (not rely on a subsequent ALTER)."""
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "task_path TEXT NOT NULL DEFAULT ''" in src


def test_migration_prepopulates_tracking_table() -> None:
    """Must insert rows 0..N-1 into `checkpoint_migrations` so that a
    subsequent PostgresSaver.setup() treats schema as up-to-date."""
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "INSERT INTO checkpoint_migrations (v) VALUES" in src
    assert "_LANGGRAPH_MIGRATIONS_COUNT = 10" in src
