"""Variable Aggregator — combine outputs from multiple upstream branches."""
from __future__ import annotations

from typing import Any

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class VariableAggregatorNode(AbstractNode):
    manifest = NodeManifest(
        type="variable-aggregator",
        category="logic",
        name="Variable Aggregator",
        description="Combine outputs from multiple upstream branches.",
    )
    io = NodeIO()
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["first_non_null", "array", "merge_object"],
                    "default": "first_non_null",
                },
            },
        },
    )

    async def execute(self, ctx: NodeContext) -> NodeResult:
        mode = ctx.config.get("mode", "first_non_null")
        values = list(ctx.inputs.values())

        if mode == "first_non_null":
            for v in values:
                if v not in (None, ""):
                    return NodeResult(outputs={"output": v})
            return NodeResult(outputs={"output": None})

        if mode == "array":
            return NodeResult(outputs={"output": [v for v in values if v is not None]})

        if mode == "merge_object":
            merged: dict[str, Any] = {}
            for v in values:
                if isinstance(v, dict):
                    merged.update(v)
            return NodeResult(outputs={"output": merged})

        raise ValueError(f"Variable Aggregator: unknown mode '{mode}'")
