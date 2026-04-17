"""Azure OpenAI Provider — uses openai.AsyncAzureOpenAI."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import structlog
from openai import AsyncAzureOpenAI

from app.model.providers.base import BaseProvider, FieldSchema
from app.model.providers import register_provider

logger = structlog.get_logger(__name__)

_DEFAULT_API_VERSION = "2024-10-21"


@register_provider
class AzureProvider(BaseProvider):

    @classmethod
    def supported_types(cls) -> list[str]:
        return ["azure"]

    @classmethod
    def display_label(cls, type_: str) -> str:
        return "Azure OpenAI"

    @classmethod
    def required_fields(cls, type_: str) -> list[FieldSchema]:
        return [
            {"name": "api_key", "label": "API Key",
             "required": True, "type": "password"},
            {"name": "base_url", "label": "Endpoint",
             "required": True, "type": "url",
             "placeholder": "https://<resource>.openai.azure.com"},
            {"name": "api_version", "label": "API Version",
             "required": True, "type": "text",
             "default": _DEFAULT_API_VERSION},
        ]

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["llm", "embedding"]

    def _client(
        self, base_url: str | None, api_key: str | None, api_version: str | None,
    ) -> AsyncAzureOpenAI:
        if not api_key:
            raise ValueError("Azure Provider requires api_key")
        if not base_url:
            raise ValueError("Azure Provider requires base_url (endpoint)")
        return AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=base_url.rstrip("/"),
            api_version=api_version or _DEFAULT_API_VERSION,
            timeout=60.0,
            max_retries=0,
        )

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        api_version = kwargs.pop("api_version", None)
        client = self._client(base_url, api_key, api_version)
        stream = await client.chat.completions.create(
            model=model,  # in Azure this is the deployment name
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
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
        api_version = kwargs.pop("api_version", None)
        client = self._client(base_url, api_key, api_version)
        resp = await client.chat.completions.create(
            model=model, messages=messages,
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
        client = self._client(base_url, api_key, kwargs.get("api_version"))
        resp = await client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    async def discover_models(
        self,
        *,
        type_: str,
        base_url: str | None,
        api_key: str | None,
    ) -> list[dict]:
        if not base_url or not api_key:
            raise ValueError("Azure discover requires base_url + api_key")
        url = (
            f"{base_url.rstrip('/')}/openai/models?api-version={_DEFAULT_API_VERSION}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"api-key": api_key})
                resp.raise_for_status()
                raw = resp.json().get("data", [])
        except Exception as exc:
            logger.warning("azure_discover_failed", url=url, error=str(exc))
            raise ValueError(f"Azure model discovery failed: {exc}")
        return [
            {"id": m["id"], "type_hint": self.classify_model_id(m["id"])}
            for m in raw if isinstance(m, dict) and m.get("id")
        ]
