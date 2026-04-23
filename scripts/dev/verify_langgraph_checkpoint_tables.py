"""One-shot verification that alembic migration 0019 created the
LangGraph checkpoint tables correctly. Run after `alembic upgrade head`.

Usage:
    .venv/bin/python scripts/verify_langgraph_checkpoint_tables.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg  # noqa: E402

from app.core.config import settings  # noqa: E402


EXPECTED_TABLES = {
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
}


async def main() -> int:
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE 'checkpoint%' "
            "ORDER BY table_name"
        )
        tables = {r["table_name"] for r in rows}
        print(f"tables: {sorted(tables)}")

        missing = EXPECTED_TABLES - tables
        if missing:
            print(f"FAIL — missing tables: {missing}")
            return 1

        cnt = await conn.fetchval("SELECT COUNT(*) FROM checkpoint_migrations")
        max_v = await conn.fetchval("SELECT MAX(v) FROM checkpoint_migrations")
        print(f"checkpoint_migrations rows: {cnt}, max v: {max_v}")
        if cnt != 10 or max_v != 9:
            print(f"FAIL — expected 10 rows with max v=9, got {cnt}/{max_v}")
            return 1

        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='checkpoint_writes' "
            "ORDER BY ordinal_position"
        )
        col_names = [r["column_name"] for r in cols]
        print(f"checkpoint_writes cols: {col_names}")
        if "task_path" not in col_names:
            print("FAIL — checkpoint_writes.task_path missing")
            return 1

        indexes = await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND indexname LIKE 'checkpoint%thread_id%' "
            "ORDER BY indexname"
        )
        idx_names = {r["indexname"] for r in indexes}
        print(f"thread_id indexes: {sorted(idx_names)}")
        expected_idx = {
            "checkpoints_thread_id_idx",
            "checkpoint_blobs_thread_id_idx",
            "checkpoint_writes_thread_id_idx",
        }
        idx_missing = expected_idx - idx_names
        if idx_missing:
            print(f"FAIL — missing indexes: {idx_missing}")
            return 1

        print("\nOK — alembic migration 0019 schema verified.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
