"""ExecutionContext — shared state the scheduler passes to every node.

Two resolution paths:
- `resolve_selector([node_id, field, ...])`  — structured config fields
- `resolve_template("text {{#node.field#}}")` — free text, prompts, etc.

Unknown references raise. Silent fallback to empty strings makes prompt bugs
invisible at test time, which has been a repeated pain point in other
workflow systems (Dify / LangChain PromptTemplate). We err on the loud side.
"""
from __future__ import annotations

import re
from typing import Any

# {{#node_id.field#}} for node outputs; {{vars.name}} or {{vars.name.sub.0}}
# for workflow variables (supports dotted paths into dicts / list indices).
_TEMPLATE_RE = re.compile(r"\{\{#\s*(?P<node>[a-zA-Z0-9_]+)\.(?P<path>[a-zA-Z0-9_.\[\]0-9]+)\s*#\}\}")
_VAR_RE = re.compile(r"\{\{\s*vars\.(?P<path>[a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


class SelectorError(KeyError):
    """Raised when a selector or template references an unknown node / field."""


class ExecutionContext:
    def __init__(
        self,
        *,
        workflow_variables: dict[str, Any] | None = None,
        trigger_input: dict[str, Any] | None = None,
    ) -> None:
        self.workflow_variables: dict[str, Any] = dict(workflow_variables or {})
        # Trigger input is surfaced as `vars.trigger` so templates / selectors
        # can reach it without a special keyword.
        if trigger_input:
            self.workflow_variables["trigger"] = trigger_input
        self.node_outputs: dict[str, dict[str, Any]] = {}

    def record_output(self, node_id: str, output: dict[str, Any]) -> None:
        self.node_outputs[node_id] = dict(output)

    def resolve_selector(self, selector: list[str]) -> Any:
        """Resolve `[node_id, field, ...]`. `node_id == 'vars'` taps into
        workflow_variables (including the nested `trigger` blob).
        """
        if not selector or len(selector) < 2:
            raise SelectorError(f"Selector must have at least [node_id, field]: {selector}")
        node_id, *path = selector
        if node_id == "vars":
            return _dig(self.workflow_variables, path)
        if node_id not in self.node_outputs:
            raise SelectorError(f"Node '{node_id}' has no recorded output yet")
        return _dig(self.node_outputs[node_id], path)

    def resolve_template(self, text: str) -> str:
        """Substitute all `{{#node.field#}}` and `{{vars.name}}` occurrences.
        Returns `text` unchanged if no markers are present.
        """

        def _node_sub(m: re.Match) -> str:
            node = m.group("node")
            path = m.group("path").split(".")
            return _stringify(self.resolve_selector([node, *path]))

        def _var_sub(m: re.Match) -> str:
            path = m.group("path").split(".")
            head = path[0]
            if head not in self.workflow_variables:
                raise SelectorError(f"Workflow variable '{head}' not defined")
            return _stringify(_dig(self.workflow_variables[head], path[1:]))

        text = _TEMPLATE_RE.sub(_node_sub, text)
        text = _VAR_RE.sub(_var_sub, text)
        return text


def _dig(root: Any, path: list[str]) -> Any:
    cur = root
    for part in path:
        if isinstance(cur, dict):
            if part not in cur:
                raise SelectorError(
                    f"Field '{part}' not found; available: {list(cur.keys())}"
                )
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError) as e:
                raise SelectorError(f"Invalid list index '{part}': {e}") from e
        else:
            raise SelectorError(f"Cannot descend into non-container at '{part}'")
    return cur


def _stringify(val: Any) -> str:
    if isinstance(val, str):
        return val
    if val is None:
        return ""
    return str(val)
