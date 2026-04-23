"""Human Approval — pause the workflow for user input.

``langgraph.types.interrupt(value)`` raises ``GraphInterrupt`` which the
checkpointer + event bridge handle to publish a ``waiting_input`` event.
The frontend then surfaces a modal, collects user input, and POSTs it to
the resume API, which calls ``compiled.ainvoke(Command(resume=value))``.
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


class HumanApprovalNode(AbstractNode):
    manifest = NodeManifest(
        type="human_approval",
        category="extension",
        name="Human Approval",
        description="Pause for a human to approve / reject / provide input.",
    )
    io = NodeIO(
        inputs={"prompt": {"type": "string"}},
        outputs={"decision": {"type": ["string", "boolean", "object"]}},
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text shown to the approver; supports variable references.",
                },
                "approvers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of user roles or ids allowed to resume.",
                },
            },
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if ctx.config.get("prompt") is None and "prompt" not in ctx.inputs:
            raise ValueError(
                "HumanApproval: requires either config.prompt or an upstream "
                "binding for the 'prompt' input"
            )

    async def execute(self, ctx: NodeContext) -> NodeResult:
        from langgraph.types import interrupt

        prompt_text = ctx.inputs.get("prompt") or ctx.config.get("prompt") or ""

        payload = {
            "prompt": prompt_text,
            "approvers": ctx.config.get("approvers") or [],
            "node_id": ctx.node_id,
        }

        # Raises GraphInterrupt the first time; LangGraph checkpoints state
        # and returns control to the caller. On resume (via Command(resume=...))
        # interrupt() returns the user-supplied value.
        decision = interrupt(payload)

        return NodeResult(outputs={"decision": decision})
