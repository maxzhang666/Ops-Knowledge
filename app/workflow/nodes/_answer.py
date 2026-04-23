"""Answer node — terminal, optional streaming.

The scheduler resolves templates in `node.data.inputs.answer` before
execute runs. execute() just emits the resolved string as the final output.
on_stream() chunks the same text for SSE passthrough when `stream=true`.

When upstream is a live LLM stream, the scheduler forwards the LLM node's
stream_chunk events directly — Answer's own on_stream is for template-only
flows where the text is already fully rendered.
"""
from __future__ import annotations

from typing import AsyncGenerator

from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
    NodeStreamChunk,
)


class AnswerNode(AbstractNode):
    manifest = NodeManifest(
        type="answer",
        category="output",
        name="Answer",
        description="Render final response. Streams chunks when upstream is static.",
        streaming=True,
        is_terminal=True,
    )
    io = NodeIO(
        inputs={"answer": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "stream": {"type": "boolean", "default": True},
            },
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        if "answer" not in ctx.inputs:
            raise ValueError("Answer: missing 'answer' input — bind via data.inputs")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        text = ctx.inputs.get("answer") or ""
        return NodeResult(outputs={"answer": text})

    async def on_stream(self, ctx: NodeContext) -> AsyncGenerator[NodeStreamChunk, None]:
        if not ctx.config.get("stream", True):
            return
        text = ctx.inputs.get("answer") or ""
        CHUNK = 16
        for i in range(0, len(text), CHUNK):
            yield NodeStreamChunk(delta=text[i : i + CHUNK])
