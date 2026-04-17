"""Provider adapter abstract base.

Each concrete Provider implements this interface using its vendor's official
SDK. See ``docs/superpowers/specs/ops-knowledge/15-model-layer.md`` for design.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Literal, TypedDict


class FieldSchema(TypedDict, total=False):
    name: str
    label: str
    required: bool
    type: Literal["text", "password", "url", "select"]
    placeholder: str
    default: str
    options: list[str]


class BaseProvider(ABC):
    """Abstract Provider. Stateless: one instance handles many calls."""

    # ── Metadata ──────────────────────────────────────────────

    @classmethod
    @abstractmethod
    def supported_types(cls) -> list[str]:
        """``provider.type`` values this impl handles."""

    @classmethod
    def display_label(cls, type_: str) -> str:
        """Human-readable name for UI. Default: capitalize type."""
        return type_.replace("_", " ").title()

    @classmethod
    @abstractmethod
    def required_fields(cls, type_: str) -> list[FieldSchema]:
        """Credential fields for the create/edit form."""

    @classmethod
    def capabilities(cls) -> list[str]:
        """Subset of {'llm', 'embedding', 'reranker'}."""
        return ["llm", "embedding"]

    # ── Core calls (must yield OpenAI chat.completion.chunk format) ──

    @abstractmethod
    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """Stream chat completion chunks.

        Each yielded dict must match OpenAI's ChatCompletionChunk schema:
            {"choices": [{"delta": {"content"?: str, "role"?: str,
                                    "reasoning_content"?: str},
                          "finish_reason"?: str}],
             "usage"?: {"prompt_tokens": int, "completion_tokens": int}}
        """

    @abstractmethod
    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> dict:
        """Non-streaming chat. Return dict with 'choices' and 'usage'."""

    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> list[list[float]]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement embed()"
        )

    async def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        base_url: str | None,
        api_key: str | None,
        top_n: int | None = None,
    ) -> list[dict]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement rerank()"
        )

    # ── Discovery ────────────────────────────────────────────

    @abstractmethod
    async def discover_models(
        self,
        *,
        type_: str,
        base_url: str | None,
        api_key: str | None,
    ) -> list[dict]:
        """Return [{"id": str, "type_hint": "llm"|"embedding"|"reranker"}, ...]."""

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def classify_model_id(model_id: str) -> str:
        """Heuristic: embed/rerank keyword in id → embedding/reranker."""
        lower = model_id.lower()
        if "embed" in lower:
            return "embedding"
        if "rerank" in lower:
            return "reranker"
        return "llm"
