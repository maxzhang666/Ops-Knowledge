"""If-Else node — emits `branch=<id>` so scheduler's conditional routing
activates exactly one downstream edge (matching `sourceHandle`).
"""
from __future__ import annotations

from typing import Any, Callable

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)

Op = Callable[[Any, Any], bool]

_OPS: dict[str, Op] = {
    "eq":             lambda a, b: a == b,
    "neq":            lambda a, b: a != b,
    "gt":             lambda a, b: a is not None and b is not None and a > b,
    "gte":            lambda a, b: a is not None and b is not None and a >= b,
    "lt":             lambda a, b: a is not None and b is not None and a < b,
    "lte":            lambda a, b: a is not None and b is not None and a <= b,
    "contains":       lambda a, b: b in a if a is not None else False,
    "not_contains":   lambda a, b: b not in a if a is not None else True,
    "is_empty":       lambda a, _b: a in (None, "", [], {}, ()),
    "not_empty":      lambda a, _b: a not in (None, "", [], {}, ()),
    "starts_with":    lambda a, b: isinstance(a, str) and a.startswith(b),
    "ends_with":      lambda a, b: isinstance(a, str) and a.endswith(b),
}


def _eval_rule(rule: dict, ctx: NodeContext) -> bool:
    op = rule.get("operator")
    if op not in _OPS:
        raise ValueError(f"If-Else: unknown operator '{op}'")
    var = rule.get("variable")
    if isinstance(var, str) and var in ctx.inputs:
        lhs = ctx.inputs[var]
    elif isinstance(var, list) and ctx.execution_context is not None:
        try:
            lhs = ctx.execution_context.resolve_selector(var)
        except Exception:
            lhs = None
    else:
        lhs = None
    return _OPS[op](lhs, rule.get("value"))


def _eval_condition(cond: dict, ctx: NodeContext) -> bool:
    rules = cond.get("rules") or []
    if not rules:
        return False
    results = [_eval_rule(r, ctx) for r in rules]
    logic = (cond.get("logic") or "and").lower()
    return all(results) if logic == "and" else any(results)


class IfElseNode(AbstractNode):
    manifest = NodeManifest(
        type="if-else",
        category="logic",
        name="If-Else",
        description="Branch on boolean conditions. First matching condition wins.",
    )
    io = NodeIO()
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "logic": {"type": "string", "enum": ["and", "or"], "default": "and"},
                            "rules": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "variable": {},
                                        "operator": {"type": "string"},
                                        "value": {},
                                    },
                                    "required": ["variable", "operator"],
                                },
                            },
                        },
                        "required": ["id", "rules"],
                    },
                },
            },
            "required": ["conditions"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if not ctx.config.get("conditions"):
            raise ValueError("If-Else: at least one condition required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        for cond in ctx.config["conditions"]:
            if _eval_condition(cond, ctx):
                return NodeResult(outputs={}, branch=cond["id"])
        return NodeResult(outputs={}, branch="else")
