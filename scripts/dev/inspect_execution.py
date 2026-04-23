"""Dump an execution's status/error + its NodeExecution rows.

Usage:
    .venv/bin/python scripts/inspect_execution.py <execution_id>
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg  # noqa: E402

from app.core.config import settings  # noqa: E402


async def main(exec_id: str) -> int:
    url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://", 1,
    )
    c = await asyncpg.connect(url)
    try:
        r = await c.fetchrow(
            "SELECT status, error, trigger_input, output, started_at, finished_at "
            "FROM workflow_executions WHERE id=$1",
            exec_id,
        )
        if r is None:
            print(f"no execution with id {exec_id}")
            return 1
        print(f"execution: {exec_id}")
        print(f"  status       : {r['status']}")
        print(f"  error        : {r['error']}")
        print(f"  started_at   : {r['started_at']}")
        print(f"  finished_at  : {r['finished_at']}")
        print(f"  trigger_input: {r['trigger_input']}")
        print(f"  output       : {r['output']}")

        nodes = await c.fetch(
            "SELECT node_id, node_type, status, input_data, output_data, error "
            "FROM node_executions WHERE execution_id=$1 ORDER BY started_at",
            exec_id,
        )
        print(f"\nnode executions: {len(nodes)}")
        for n in nodes:
            print(
                f"  - id={n['node_id']} type={n['node_type']} status={n['status']}"
            )
            if n["input_data"]:
                print(f"      input : {n['input_data']}")
            if n["output_data"]:
                print(f"      output: {n['output_data']}")
            if n["error"]:
                print(f"      error : {n['error']}")

        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <execution_id>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
