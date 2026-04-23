"""Variable Splitter — project fields out of an object/array input into named outputs."""
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


class VariableSplitterNode(AbstractNode):
    manifest = NodeManifest(
        type="variable-splitter",
        category="logic",
        name="Variable Splitter",
        description="Project fields out of an object/array input into named outputs.",
    )
    io = NodeIO(inputs={"source": {"type": ["object", "array"]}})
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "mapping": {
                    "type": "object",
                    "description": "output_name → dotted/bracket path into 'source'",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["mapping"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not ctx.config.get("mapping"):
            raise ValueError("Variable Splitter: mapping required")
        if "source" not in ctx.inputs:
            raise ValueError("Variable Splitter: 'source' input required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        src = ctx.inputs["source"]
        mapping: dict[str, str] = ctx.config["mapping"]
        outputs: dict[str, Any] = {}
        for out_name, path in mapping.items():
            try:
                outputs[out_name] = _dig(src, path)
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"Variable Splitter: path '{path}' failed: {e}")
        return NodeResult(outputs=outputs)


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur[part]
        elif isinstance(cur, list):
            cur = cur[int(part)]
        else:
            raise TypeError(f"cannot descend into {type(cur).__name__} at '{part}'")
    return cur
