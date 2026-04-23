"""Unified Node Interface — every node implements the same protocol.

Executor contract (scheduler ↔ node):

1. Scheduler resolves `node.data.inputs` map into `ctx.inputs` before calling
   `validate()` / `execute()`. See INPUTS_CONVENTION below for the wire shape.
2. Scheduler calls `validate(ctx)` — node raises on invalid input / config.
3. Scheduler calls `execute(ctx)` under the node's configured timeout.
   Non-streaming nodes return NodeResult directly.
   Streaming nodes additionally yield via `on_stream(ctx)`; the scheduler
   consumes both concurrently but still requires `execute()` to return a final
   NodeResult for persistence.
4. On exception: scheduler calls `on_error(ctx, exc)`. Returning a NodeResult
   means "recovered, use this output". Returning None (default) lets the DSL
   `error_handling` block take over (retry / default-value / fail-branch / abort).
5. Cancellation: nodes must be cancellation-safe — long-running ops must
   `await` periodically so `asyncio.CancelledError` can propagate.
6. Nodes MUST NOT mutate ExecutionContext directly — only return NodeResult.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


INPUTS_CONVENTION = """
Node DSL `data.inputs` shape:

  "inputs": {
    "<input_name>": ["node_id", "field", ...],   # selector (structured)
    "<input_name>": "Some text {{#node.field#}}" # template (free text)
    "<input_name>": 42                            # literal (passed through)
  }

Rules:
- Keys must be declared in `NodeIO.inputs` (scheduler validates).
- Selector arrays resolve via ExecutionContext.resolve_selector.
- String values resolve via ExecutionContext.resolve_template — strings without
  `{{...}}` markers are returned verbatim.
- Literals (number / bool / list / dict) are passed through unchanged.
- Unknown references raise SelectorError — do NOT silently fall back.

Nodes may additionally read arbitrary DSL fields via `ctx.config` (the entire
raw `data` dict), but anything declared in `io.inputs` MUST come through the
resolved `ctx.inputs` path.
"""


class NodeManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = Field(..., min_length=1, max_length=50)
    type_version: str = "1.0"
    category: Literal[
        "trigger", "knowledge", "llm", "agent",
        "logic", "extension", "output", "memory",
    ]
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    icon: str | None = None
    author: str = "builtin"
    streaming: bool = False  # True if node uses on_stream
    is_terminal: bool = False  # e.g. Answer
    is_compound: bool = False  # e.g. Iteration / Loop


class NodeIO(BaseModel):
    """Input / output contract. Values are JSON Schema fragments that the
    frontend and scheduler use to type-check."""
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


class NodeConfigForm(BaseModel):
    """Declarative form schema — frontend auto-renders this.
    `schema` follows JSON Schema draft 2020-12. `ui_schema` is a react-
    jsonschema-form / shadcn-autoform style hint layer."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: dict[str, Any] = Field(alias="schema", default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)


class NodeContext(BaseModel):
    """Passed to execute(). Scheduler injects the real ExecutionContext handle;
    nodes read it via `ctx.execution_context` if they need cross-node state."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    node_id: str
    node_type: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    execution_context: Any | None = None
    trace_id: str | None = None


class NodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: dict[str, Any] = Field(default_factory=dict)
    branch: str | None = None  # for conditional nodes → activates one sourceHandle
    token_usage: dict[str, int] | None = None  # Langfuse plan 23 consumes
    debug: dict[str, Any] | None = None


class NodeStreamChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: str
    meta: dict[str, Any] | None = None


@runtime_checkable
class BaseNode(Protocol):
    """All nodes implement this — built-in or plugin, same contract."""

    manifest: NodeManifest
    io: NodeIO
    config_form: NodeConfigForm

    async def execute(self, ctx: NodeContext) -> NodeResult: ...

    async def validate(self, ctx: NodeContext) -> None: ...

    async def on_stream(self, ctx: NodeContext) -> AsyncGenerator[NodeStreamChunk, None]: ...

    async def on_error(
        self, ctx: NodeContext, exc: Exception
    ) -> NodeResult | None: ...


class AbstractNode:
    """Convenience base with no-op defaults. Concrete nodes override `execute`,
    and selectively `validate` / `on_stream` / `on_error`."""

    manifest: NodeManifest
    io: NodeIO = NodeIO()
    config_form: NodeConfigForm = NodeConfigForm()

    async def execute(self, ctx: NodeContext) -> NodeResult:  # pragma: no cover
        raise NotImplementedError

    async def validate(self, ctx: NodeContext) -> None:
        return None

    async def on_stream(self, ctx: NodeContext):
        # Default: empty async generator.
        if False:
            yield  # pragma: no cover

    async def on_error(self, ctx: NodeContext, exc: Exception) -> NodeResult | None:
        return None
