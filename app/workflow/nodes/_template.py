"""Template node — Jinja2 with sandboxed environment + StrictUndefined.

Sandbox blocks dangerous attribute access (e.g. `{{ "".__class__ }}`).
StrictUndefined raises on unknown variables rather than silently rendering empty.
"""
from __future__ import annotations

from jinja2 import StrictUndefined, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)

_JINJA = SandboxedEnvironment(
    autoescape=select_autoescape(enabled_extensions=()),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


class TemplateNode(AbstractNode):
    manifest = NodeManifest(
        type="template",
        category="extension",
        name="Template",
        description="Render a Jinja2 template over upstream variables.",
    )
    io = NodeIO(outputs={"output": {"type": "string"}})
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "template": {"type": "string", "minLength": 1},
            },
            "required": ["template"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        tmpl_str = ctx.config.get("template")
        if not tmpl_str:
            raise ValueError("Template: missing 'template' config")
        try:
            _JINJA.from_string(tmpl_str)
        except Exception as e:
            raise ValueError(f"Template: invalid Jinja2 syntax: {e}")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        tmpl = _JINJA.from_string(ctx.config["template"])
        try:
            rendered = tmpl.render(**ctx.inputs)
        except Exception as e:
            raise RuntimeError(f"Template render failed: {e}")
        return NodeResult(outputs={"output": rendered})
