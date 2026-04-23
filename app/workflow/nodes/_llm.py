"""LLM node — delegates to 1a's ModelService.

Streaming chunks follow OpenAI-compat shape:
  {"choices": [{"delta": {"content": "..."}}], "usage": {...}}

Known limitation: execute() and on_stream() each open their own chat_stream
iterator. Plan 22 (Workflow Agent) replaces this with a shared asyncio.Queue
fan-out once we have SSE validation in place.
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator

from app.core.database import async_session
from app.core.observability import capture_io_enabled
from app.model.service import ModelService
from app.observability.workflow_instrument import current_trace
from app.workflow.nodes.base import (
    AbstractNode,
    NodeConfigForm,
    NodeContext,
    NodeIO,
    NodeManifest,
    NodeResult,
    NodeStreamChunk,
)


class LLMNode(AbstractNode):
    manifest = NodeManifest(
        type="llm",
        category="llm",
        name="LLM",
        description="Call an LLM with a prompt template. Supports streaming.",
        streaming=True,
    )
    io = NodeIO(
        inputs={"query": {"type": "string"}, "context": {"type": "string"}},
        outputs={
            "content": {"type": "string"},
            "token_usage": {"type": "object"},
        },
    )
    config_form = NodeConfigForm(
        schema={
            "type": "object",
            "properties": {
                "model_provider_id": {"type": "string", "format": "uuid"},
                "model_name": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2, "default": 0.7},
                "max_tokens": {"type": "integer", "minimum": 1, "default": 2048},
                "streaming": {"type": "boolean", "default": True},
                "prompt_template": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                            "text": {"type": "string"},
                        },
                        "required": ["role", "text"],
                    },
                },
            },
            "required": ["model_provider_id", "model_name", "prompt_template"],
        },
    )

    async def validate(self, ctx: NodeContext) -> None:
        for key in ("model_provider_id", "model_name", "prompt_template"):
            if not ctx.config.get(key):
                raise ValueError(f"LLM: missing required config '{key}'")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        messages = self._render_messages(ctx)
        pid = uuid.UUID(str(ctx.config["model_provider_id"]))
        model = ctx.config["model_name"]
        extras = {
            "temperature": ctx.config.get("temperature", 0.7),
            "max_tokens": ctx.config.get("max_tokens", 2048),
            "trace_id": ctx.trace_id,
        }

        # Attach a Langfuse Generation span when we're inside a workflow trace.
        trace = current_trace.get()
        gen = trace.generation(
            name="llm.generation",
            model=model,
            input=messages if capture_io_enabled() else None,
        ) if trace is not None else None

        if ctx.config.get("streaming", True):
            pieces: list[str] = []
            usage: dict = {}
            async with async_session() as db:
                svc = ModelService(db)
                async for chunk in svc.chat_stream(pid, model, messages, **extras):
                    content = _extract_delta(chunk)
                    if content:
                        pieces.append(content)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
            if gen is not None:
                gen.end(usage={
                    "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "output_tokens": int(usage.get("completion_tokens", 0) or 0),
                })
            return NodeResult(
                outputs={"content": "".join(pieces), "token_usage": usage},
                token_usage=usage or None,
            )

        async with async_session() as db:
            svc = ModelService(db)
            resp = await svc.chat(pid, model, messages, **extras)
        usage = resp.get("usage") or {}
        if gen is not None:
            gen.end(usage={
                "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "output_tokens": int(usage.get("completion_tokens", 0) or 0),
            })
        return NodeResult(
            outputs={
                "content": resp["choices"][0]["message"]["content"],
                "token_usage": usage,
            },
            token_usage=usage or None,
        )

    async def on_stream(self, ctx: NodeContext) -> AsyncGenerator[NodeStreamChunk, None]:
        if not ctx.config.get("streaming", True):
            return
        messages = self._render_messages(ctx)
        pid = uuid.UUID(str(ctx.config["model_provider_id"]))
        model = ctx.config["model_name"]
        extras = {
            "temperature": ctx.config.get("temperature", 0.7),
            "max_tokens": ctx.config.get("max_tokens", 2048),
            "trace_id": ctx.trace_id,
        }
        async with async_session() as db:
            svc = ModelService(db)
            async for chunk in svc.chat_stream(pid, model, messages, **extras):
                content = _extract_delta(chunk)
                if content:
                    yield NodeStreamChunk(delta=content)

    def _render_messages(self, ctx: NodeContext) -> list[dict]:
        """Apply lightweight str.format() over resolved inputs + scalar
        workflow vars. Missing placeholders are left as-is so authors see
        them in the trace rather than silently empty-stringing."""
        tmpl: list[dict] = ctx.config["prompt_template"]
        rendered = []
        ns = dict(ctx.inputs)
        for k, v in _flat_workflow_vars(ctx).items():
            ns.setdefault(k, v)
        for msg in tmpl:
            text = msg["text"]
            try:
                text = text.format(**ns)
            except (KeyError, IndexError):
                pass
            rendered.append({"role": msg["role"], "content": text})
        return rendered


def _flat_workflow_vars(ctx: NodeContext) -> dict:
    if ctx.execution_context is None:
        return {}
    return {
        k: v for k, v in ctx.execution_context.workflow_variables.items()
        if not isinstance(v, dict)
    }


def _extract_delta(chunk: dict) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return delta.get("content") or ""
