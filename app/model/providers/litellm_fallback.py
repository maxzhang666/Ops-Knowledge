"""LiteLLM-backed Provider for long-tail vendors.

Covers vendors where writing a dedicated official-SDK adapter isn't justified
(Bedrock, Vertex AI, Cohere, Mistral, Hugging Face, Replicate, Watsonx, ...).
LiteLLM handles the SDK translation for these.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import litellm
import structlog

from app.model.providers.base import BaseProvider, FieldSchema
from app.model.providers import register_provider

logger = structlog.get_logger(__name__)


_LABELS = {
    "bedrock": "AWS Bedrock",
    "vertex_ai": "Google Vertex AI",
    "cohere": "Cohere",
    "mistral": "Mistral",
    "huggingface": "Hugging Face",
    "replicate": "Replicate",
    "watsonx": "IBM Watsonx",
}

# Known models per type — best-effort; users can still manually add via registry.
_KNOWN_MODELS: dict[str, list[dict]] = {
    "cohere": [
        {"id": "command-r-plus", "type_hint": "llm"},
        {"id": "command-r", "type_hint": "llm"},
        {"id": "embed-english-v3.0", "type_hint": "embedding"},
        {"id": "embed-multilingual-v3.0", "type_hint": "embedding"},
        {"id": "rerank-english-v3.0", "type_hint": "reranker"},
        {"id": "rerank-multilingual-v3.0", "type_hint": "reranker"},
    ],
    "mistral": [
        {"id": "mistral-large-latest", "type_hint": "llm"},
        {"id": "mistral-small-latest", "type_hint": "llm"},
        {"id": "mistral-embed", "type_hint": "embedding"},
    ],
    "bedrock": [
        {"id": "anthropic.claude-sonnet-4-20250514-v1:0", "type_hint": "llm"},
        {"id": "amazon.titan-embed-text-v2:0", "type_hint": "embedding"},
    ],
    "vertex_ai": [
        {"id": "gemini-2.0-flash", "type_hint": "llm"},
        {"id": "gemini-2.0-pro", "type_hint": "llm"},
        {"id": "text-embedding-004", "type_hint": "embedding"},
    ],
}


@register_provider
class LiteLLMFallbackProvider(BaseProvider):

    @classmethod
    def supported_types(cls) -> list[str]:
        return list(_LABELS.keys())

    @classmethod
    def display_label(cls, type_: str) -> str:
        return _LABELS.get(type_, type_.title())

    @classmethod
    def required_fields(cls, type_: str) -> list[FieldSchema]:
        # These vendors have varied auth; api_key is the common required field.
        # Bedrock / Vertex need additional creds configured via environment
        # (AWS profile, GCP service account). Document this in UI help text.
        base: list[FieldSchema] = [
            {"name": "api_key", "label": "API Key",
             "required": type_ not in ("bedrock", "vertex_ai"),
             "type": "password",
             "placeholder": "(Bedrock/Vertex use AWS/GCP env credentials)"
             if type_ in ("bedrock", "vertex_ai") else ""},
            {"name": "base_url", "label": "Base URL (optional)",
             "required": False, "type": "url"},
        ]
        return base

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["llm", "embedding", "reranker"]

    # ── core ─────────────────────────────────────────────────

    @staticmethod
    def _litellm_kwargs(base_url: str | None, api_key: str | None) -> dict:
        kw: dict = {}
        if base_url:
            kw["api_base"] = base_url
        if api_key:
            kw["api_key"] = api_key
        return kw

    def _qualify(self, type_: str, model: str) -> str:
        return model if "/" in model else f"{type_}/{model}"

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        type_hint = kwargs.pop("_type_hint", "")
        qualified = self._qualify(type_hint, model) if type_hint else model
        kwargs.setdefault("timeout", 60)
        stream = await litellm.acompletion(
            model=qualified, messages=messages, stream=True,
            stream_options={"include_usage": True},
            **self._litellm_kwargs(base_url, api_key),
            **{k: v for k, v in kwargs.items() if not k.startswith("_")},
        )
        async for chunk in stream:
            yield chunk.model_dump()

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> dict:
        type_hint = kwargs.pop("_type_hint", "")
        qualified = self._qualify(type_hint, model) if type_hint else model
        kwargs.setdefault("timeout", 60)
        resp = await litellm.acompletion(
            model=qualified, messages=messages,
            **self._litellm_kwargs(base_url, api_key),
            **{k: v for k, v in kwargs.items() if not k.startswith("_")},
        )
        return resp.model_dump()

    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> list[list[float]]:
        resp = await litellm.aembedding(
            model=model, input=texts,
            **self._litellm_kwargs(base_url, api_key),
        )
        return [d["embedding"] for d in resp.data]

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
        resp = await litellm.arerank(
            model=model, query=query, documents=documents,
            top_n=top_n,
            **self._litellm_kwargs(base_url, api_key),
        )
        return resp.results if hasattr(resp, "results") else resp.get("results", [])

    async def discover_models(
        self,
        *,
        type_: str,
        base_url: str | None,
        api_key: str | None,
    ) -> list[dict]:
        return _KNOWN_MODELS.get(type_, [])
