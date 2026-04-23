"""code_execute — runs Python in the Docker Runner sandbox.

Reuses the Plan 8 Runner (already sandboxed: non-root, memory-limited,
network-off). No additional host-side isolation needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from app.workflow.runner_client import RunnerClient, RunnerError

if TYPE_CHECKING:
    from app.agent.tools import ToolContext


def make_code_execute(ctx: "ToolContext") -> BaseTool:  # noqa: ARG001
    """ctx is accepted for factory-signature uniformity; code_execute
    doesn't capture any request-scoped handles — the Runner client is
    stateless."""

    @tool
    async def code_execute(code: str, timeout: int = 10) -> str:
        """Execute Python code in an isolated sandbox. Returns stdout or the
        error message. Use for math, data transformation, small scripts.

        Network access is disabled. ``timeout`` in seconds (max 30).
        Imports limited to the Runner's pre-installed libraries
        (stdlib + numpy + pandas + requests is NOT available — use
        http_request tool for external calls).
        """
        client = RunnerClient()
        try:
            result = await client.execute(
                code=code,
                timeout=float(min(max(timeout, 1), 30)),
            )
        except RunnerError as e:
            return f"Runner error: {e}"
        except Exception as e:  # noqa: BLE001
            return f"Execution failed: {str(e)[:300]}"

        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        if result.get("status") != "ok":
            return f"[error] {stderr or result.get('error') or 'unknown'}"
        if stderr:
            return f"{stdout}\n[stderr] {stderr}"
        return stdout or "(no output)"

    return code_execute
