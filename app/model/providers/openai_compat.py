"""OpenAI-compatible Provider.

Handles OpenAI itself plus every vendor that exposes an OpenAI-shaped
``/v1/chat/completions`` endpoint: DeepSeek, Ollama, OpenRouter, Groq,
Together, Fireworks, Perplexity, vLLM, Xinference, LMStudio, xAI, and any
``custom`` or unknown type. Also the default fallback for unregistered types.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import structlog
from openai import AsyncOpenAI

from app.model.providers.base import BaseProvider, FieldSchema
from app.model.providers import register_provider

logger = structlog.get_logger(__name__)


_LABELS = {
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "together_ai": "Together AI",
    "fireworks_ai": "Fireworks AI",
    "perplexity": "Perplexity",
    "xai": "xAI",
    "vllm": "vLLM",
    "xinference": "Xinference",
    "lmstudio": "LM Studio",
    "custom": "Custom (OpenAI-compatible)",
}

_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together_ai": "https://api.together.xyz/v1",
    "fireworks_ai": "https://api.fireworks.ai/inference/v1",
    "perplexity": "https://api.perplexity.ai",
    "xai": "https://api.x.ai/v1",
}

# Types that don't need api_key (local models)
_NO_KEY_TYPES = {"ollama", "vllm", "xinference", "lmstudio"}


def _normalize_v1(url: str) -> str:
    """Ensure base_url ends with /v1 suffix the OpenAI SDK expects."""
    u = url.rstrip("/")
    if u.endswith("/v1"):
        return u
    # Some users enter "http://host:4000" (a LiteLLM proxy) without /v1
    if "/v1" not in u:
        return f"{u}/v1"
    return u


@register_provider
class OpenAICompatProvider(BaseProvider):

    @classmethod
    def supported_types(cls) -> list[str]:
        return list(_LABELS.keys())

    @classmethod
    def display_label(cls, type_: str) -> str:
        return _LABELS.get(type_, type_.replace("_", " ").title())

    @classmethod
    def required_fields(cls, type_: str) -> list[FieldSchema]:
        fields: list[FieldSchema] = []
        if type_ not in _NO_KEY_TYPES:
            fields.append({
                "name": "api_key", "label": "API Key",
                "required": True, "type": "password",
            })
        default_url = _DEFAULT_BASE_URLS.get(type_)
        fields.append({
            "name": "base_url", "label": "Base URL",
            "required": default_url is None,
            "type": "url",
            **({"default": default_url} if default_url else {}),
            **({"placeholder": "http://host:port/v1"} if not default_url else {}),
        })
        return fields

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["llm", "embedding"]

    # ── SDK factory ──────────────────────────────────────────

    def _client(self, base_url: str | None, api_key: str | None, type_hint: str = "") -> AsyncOpenAI:
        resolved_url = base_url or _DEFAULT_BASE_URLS.get(type_hint)
        if not resolved_url:
            raise ValueError(
                f"OpenAI-compatible provider '{type_hint or 'custom'}' requires base_url"
            )
        # No-key vendors accept empty string; OpenAI SDK requires non-empty
        resolved_key = api_key or "ollama"  # placeholder for local servers
        return AsyncOpenAI(
            base_url=_normalize_v1(resolved_url),
            api_key=resolved_key,
            timeout=60.0,
            max_retries=0,  # we manage retries at the pipeline level
        )

    # ── chat_stream ──────────────────────────────────────────

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
        client = self._client(base_url, api_key, type_hint)
        logger.info(
            "openai_sdk_create_before",
            resolved_base=str(client.base_url), model=model,
            msg_count=len(messages),
        )
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **{k: v for k, v in kwargs.items() if not k.startswith("_")},
            )
        except Exception:
            logger.exception("openai_sdk_create_failed", model=model)
            raise
        logger.info("openai_sdk_create_after", model=model)
        chunk_n = 0
        try:
            async for chunk in stream:
                chunk_n += 1
                if chunk_n == 1:
                    logger.info("openai_sdk_first_chunk", model=model)
                yield chunk.model_dump()
        except Exception:
            logger.exception(
                "openai_sdk_iter_failed", model=model, chunks_so_far=chunk_n,
            )
            raise
        logger.info("openai_sdk_iter_done", model=model, chunks=chunk_n)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> dict:
        client = self._client(base_url, api_key, kwargs.pop("_type_hint", ""))
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
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
        client = self._client(base_url, api_key, kwargs.get("_type_hint", ""))
        resp = await client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    # ── Discovery ────────────────────────────────────────────

    async def discover_models(
        self,
        *,
        type_: str,
        base_url: str | None,
        api_key: str | None,
    ) -> list[dict]:
        resolved_url = base_url or _DEFAULT_BASE_URLS.get(type_)
        if not resolved_url:
            raise ValueError(
                f"base_url required to discover models for type '{type_}'"
            )
        url = _normalize_v1(resolved_url)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{url}/models", headers=headers)
                resp.raise_for_status()
                raw = resp.json().get("data", [])
        except Exception as exc:
            logger.warning(
                "model_discover_failed", type=type_, url=url, error=str(exc),
            )
            raise ValueError(f"Failed to discover models from {url}: {exc}")

        return [
            {"id": m["id"], "type_hint": self.classify_model_id(m["id"])}
            for m in raw
            if isinstance(m, dict) and m.get("id")
        ]
