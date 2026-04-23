"""Dump the full checkpoint timeline for a given thread_id.

Used to verify Phase 4b: when thread_id == conversation_id, successive
turns in the same conversation accumulate checkpoints under one thread.

Usage:
    .venv/bin/python scripts/verify_thread_history.py <thread_id>

Output per checkpoint row:
    step │ checkpoint_id (short) │ recorded channel keys │ latest node outputs
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg  # noqa: E402

from app.core.config import settings  # noqa: E402


async def main(thread_id: str) -> int:
    url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://", 1,
    )
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            """
            SELECT checkpoint_id, parent_checkpoint_id, metadata
            FROM checkpoints
            WHERE thread_id = $1
            ORDER BY checkpoint_id ASC
            """,
            thread_id,
        )
        if not rows:
            print(f"no checkpoints for thread_id={thread_id}")
            print("(either the conversation never ran, or ran under a different thread)")
            return 1

        print(f"thread_id: {thread_id}")
        print(f"total checkpoints: {len(rows)}\n")
        print(f"{'#':>4}  {'checkpoint_id':<14}  {'parent':<14}  source       step  writes")
        print("-" * 80)
        for i, r in enumerate(rows, 1):
            ckpt_short = str(r["checkpoint_id"])[:12]
            parent_short = (str(r["parent_checkpoint_id"])[:12] if r["parent_checkpoint_id"] else "(root)")
            md = r["metadata"] or {}
            if isinstance(md, (bytes, bytearray, memoryview)):
                import json
                try:
                    md = json.loads(md)
                except Exception:
                    md = {}
            elif isinstance(md, str):
                import json
                try:
                    md = json.loads(md)
                except Exception:
                    md = {}
            source = str(md.get("source", "?"))[:12]
            step = md.get("step", "?")
            # ``writes`` is the dict of {node_id: {state_delta}} written at
            # this step — lets you see which node just completed.
            writes = md.get("writes") or {}
            nodes = ", ".join(sorted(writes.keys())) if writes else "—"
            if len(nodes) > 40:
                nodes = nodes[:37] + "..."
            print(f"{i:>4}  {ckpt_short:<14}  {parent_short:<14}  {source:<12} {step!s:>4}  {nodes}")

        # Turn boundaries: parent_checkpoint_id=NULL means "new invoke", i.e.
        # a new turn in this thread (for multi-turn conversations).
        roots = [r for r in rows if not r["parent_checkpoint_id"]]
        print(f"\nturn boundaries (parent=NULL): {len(roots)}")
        if len(roots) > 1:
            print("  → multi-turn accumulation detected ✓")
        elif len(roots) == 1:
            print("  → single-turn (or thread only has one invocation)")

        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <thread_id>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
