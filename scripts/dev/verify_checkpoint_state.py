"""Read back a LangGraph checkpoint by thread_id (== execution_id) and
print the last snapshotted state. Proves that checkpointing is actually
persisting the engine's state, not just writing empty rows.

Usage:
    .venv/bin/python scripts/verify_checkpoint_state.py <execution_id>

Where <execution_id> is any WorkflowExecution.id you just ran — since
Phase 4a sets thread_id == execution_id.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402


async def main(exec_id: str) -> int:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except Exception as e:
        print(f"FAIL — langgraph import error: {e}")
        return 1

    conn_string = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://", 1,
    )

    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        config = {"configurable": {"thread_id": exec_id}}
        latest = await saver.aget_tuple(config)
        if latest is None:
            print(f"FAIL — no checkpoint found for thread_id={exec_id}")
            return 1

        ckpt = latest.checkpoint
        print(f"thread_id: {exec_id}")
        print(f"checkpoint_id: {ckpt.get('id')}")
        print(f"step: {latest.metadata.get('step') if latest.metadata else '?'}")
        channel_values = ckpt.get("channel_values") or {}
        print(f"channels recorded: {sorted(channel_values.keys())}")

        # Dig into our known state keys.
        for key in ("outputs", "inputs", "branches"):
            val = channel_values.get(key)
            if val:
                print(f"\n{key}:")
                for nid, bucket in val.items():
                    print(f"  {nid}: {bucket}")

    print("\nOK — checkpoint state read back successfully.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <execution_id>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
