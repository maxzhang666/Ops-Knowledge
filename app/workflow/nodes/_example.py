"""Echo node — used for tests and as a reference implementation."""
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
)


class EchoNode(AbstractNode):
    manifest = NodeManifest(
        type="builtin.echo",
        category="extension",
        name="Echo",
        description="Echoes input.text to output.text with an optional prefix.",
    )
    io = NodeIO(
        inputs={"text": {"type": "string"}},
        outputs={"text": {"type": "string"}},
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "prefix": {"type": "string", "default": ""},
            },
        },
    )

    async def execute(self, ctx: NodeContext) -> NodeResult:
        prefix = ctx.config.get("prefix", "")
        return NodeResult(outputs={"text": f"{prefix}{ctx.inputs.get('text', '')}"})
