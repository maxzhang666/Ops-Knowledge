"""Code node — delegates execution to the Runner service (plan 16).

Inputs resolved by scheduler → passed through as Runner `inputs`. User code
may read/write them via the `inputs` / `outputs` globals (see sandbox.py).
"""
from __future__ import annotations

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)
from app.workflow.runner_client import RunnerClient, RunnerError


class CodeNode(AbstractNode):
    manifest = NodeManifest(
        type="code",
        category="extension",
        name="Code",
        description="Execute Python in the sandboxed Runner service.",
    )
    io = NodeIO()  # user-defined via DSL (outputs shape is dynamic)
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python"], "default": "python"},
                "code": {"type": "string", "minLength": 1},
                "timeout": {"type": "number", "minimum": 0.5, "maximum": 60, "default": 10},
                "memory_mb": {"type": "integer", "minimum": 32, "maximum": 512, "default": 256},
            },
            "required": ["code"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not ctx.config.get("code"):
            raise ValueError("Code: missing 'code' config")
        if ctx.config.get("language", "python") != "python":
            raise ValueError("Code: only 'python' is supported in Phase 1b")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        client = RunnerClient()
        timeout = float(ctx.config.get("timeout", 10))
        memory_limit = int(ctx.config.get("memory_mb", 256)) * 1024 * 1024

        try:
            resp = await client.execute(
                code=ctx.config["code"],
                inputs=ctx.inputs,
                timeout=timeout,
                memory_limit=memory_limit,
                request_id=ctx.trace_id,
            )
        except RunnerError as e:
            raise RuntimeError(f"Runner unreachable: {e}")

        if not resp.get("ok"):
            raise RuntimeError(f"Code execution failed: {resp.get('error')}")
        return NodeResult(
            outputs=resp.get("outputs") or {},
            debug={"stdout": resp.get("stdout"), "stderr": resp.get("stderr")},
        )
