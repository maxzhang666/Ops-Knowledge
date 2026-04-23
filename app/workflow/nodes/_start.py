"""Start node — entry point with typed variable declarations.

DSL config:
  data.variables: [{name, type, required?, default?}]

Zero-config: trigger_input is passed through as-is. With declared variables:
required ones must be present in trigger_input or validate() raises; missing
optional ones fall back to `default`.
"""
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


class StartNode(AbstractNode):
    manifest = NodeManifest(
        type="start",
        category="trigger",
        name="Start",
        description="Entry point. Declares workflow input variables.",
    )
    io = NodeIO(inputs={}, outputs={})
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "variables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["string", "number", "boolean", "object", "array"],
                            },
                            "required": {"type": "boolean", "default": False},
                            "default": {},
                        },
                        "required": ["name", "type"],
                    },
                },
            },
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        variables = ctx.config.get("variables") or []
        trigger = _trigger(ctx)
        for v in variables:
            if v.get("required") and v["name"] not in trigger:
                raise ValueError(f"Start: missing required variable '{v['name']}'")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        variables = ctx.config.get("variables") or []
        trigger = _trigger(ctx)
        outputs: dict[str, Any] = {}
        if not variables:
            outputs.update(trigger)
        else:
            for v in variables:
                name = v["name"]
                if name in trigger:
                    outputs[name] = _coerce(trigger[name], v["type"])
                elif "default" in v:
                    outputs[name] = v["default"]
        return NodeResult(outputs=outputs)


def _trigger(ctx: NodeContext) -> dict:
    if ctx.execution_context is None:
        return {}
    return ctx.execution_context.workflow_variables.get("trigger") or {}


def _coerce(value: Any, declared: str) -> Any:
    try:
        if declared == "string":
            return str(value)
        if declared == "number":
            return float(value) if "." in str(value) else int(value)
        if declared == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
    except (ValueError, TypeError):
        pass
    return value
