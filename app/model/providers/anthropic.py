"""Anthropic Provider — uses anthropic official SDK.

Normalizes Anthropic's native stream format to OpenAI ChatCompletionChunk
schema so the rest of the system stays shape-agnostic.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog

from app.model.providers.base import BaseProvider, FieldSchema
from app.model.providers import register_provider

logger = structlog.get_logger(__name__)

# Maintained here; refresh when Anthropic releases new models.
_KNOWN_MODELS = [
    "claude-opus-4-5-20250514",
    "claude-opus-4-5-20250514-v1",
    "claude-sonnet-4-6-20250929",
    "claude-sonnet-4-5-20250514",
    "claude-haiku-4-5-20251001",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


@register_provider
class AnthropicProvider(BaseProvider):

    @classmethod
    def supported_types(cls) -> list[str]:
        return ["anthropic"]

    @classmethod
    def display_label(cls, type_: str) -> str:
        return "Anthropic"

    @classmethod
    def required_fields(cls, type_: str) -> list[FieldSchema]:
        return [
            {"name": "api_key", "label": "API Key",
             "required": True, "type": "password"},
            {"name": "base_url", "label": "Base URL (optional, for proxy)",
             "required": False, "type": "url",
             "placeholder": "https://api.anthropic.com"},
        ]

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["llm"]

    # ── SDK factory ──────────────────────────────────────────

    def _client(self, base_url: str | None, api_key: str | None):
        from anthropic import AsyncAnthropic
        if not api_key:
            raise ValueError("Anthropic Provider requires api_key")
        kwargs: dict = {"api_key": api_key, "timeout": 60.0, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        return AsyncAnthropic(**kwargs)

    # ── chat_stream — normalize to OpenAI chunk format ──────────

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        client = self._client(base_url, api_key)
        system, conv = self._split_system(messages)

        create_kwargs: dict = {
            "model": model,
            "messages": conv,
            "max_tokens": kwargs.pop("max_tokens", 4096),
        }
        if system:
            create_kwargs["system"] = system
        # Preserve other useful params
        for k in ("temperature", "top_p", "stop_sequences"):
            if k in kwargs:
                create_kwargs[k] = kwargs[k]

        async with client.messages.stream(**create_kwargs) as stream:
            role_emitted = False
            usage_in = 0
            usage_out = 0
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta is None:
                        continue
                    # Text delta
                    text = getattr(delta, "text", None)
                    if text:
                        chunk = self._wrap_delta(
                            content=text, role=None if role_emitted else "assistant",
                        )
                        role_emitted = True
                        yield chunk
                    # Thinking / reasoning delta (Anthropic extended thinking)
                    thinking = getattr(delta, "thinking", None)
                    if thinking:
                        yield self._wrap_delta(reasoning_content=thinking)
                elif etype == "message_start":
                    msg = getattr(event, "message", None)
                    u = getattr(msg, "usage", None) if msg else None
                    if u:
                        usage_in = getattr(u, "input_tokens", 0) or 0
                elif etype == "message_delta":
                    u = getattr(event, "usage", None)
                    if u:
                        usage_out = getattr(u, "output_tokens", 0) or 0
                elif etype == "message_stop":
                    break

            # Final usage chunk (OpenAI-style)
            yield {
                "choices": [{
                    "index": 0, "delta": {"content": None, "role": None},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": usage_in,
                    "completion_tokens": usage_out,
                    "total_tokens": usage_in + usage_out,
                },
            }

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        base_url: str | None,
        api_key: str | None,
        **kwargs,
    ) -> dict:
        client = self._client(base_url, api_key)
        system, conv = self._split_system(messages)
        create_kwargs: dict = {
            "model": model, "messages": conv,
            "max_tokens": kwargs.pop("max_tokens", 4096),
        }
        if system:
            create_kwargs["system"] = system
        for k in ("temperature", "top_p", "stop_sequences"):
            if k in kwargs:
                create_kwargs[k] = kwargs[k]

        resp = await client.messages.create(**create_kwargs)
        text = "".join(
            b.text for b in resp.content
            if getattr(b, "type", None) == "text" and hasattr(b, "text")
        )
        return {
            "id": resp.id,
            "object": "chat.completion",
            "model": resp.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": resp.stop_reason or "stop",
            }],
            "usage": {
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
                "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            },
        }

    # ── Discovery (no /v1/models API; return known list) ──

    async def discover_models(
        self,
        *,
        type_: str,
        base_url: str | None,
        api_key: str | None,
    ) -> list[dict]:
        return [{"id": m, "type_hint": "llm"} for m in _KNOWN_MODELS]

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
        """Anthropic takes system as a top-level param, not in messages[]."""
        system_parts: list[str] = []
        conv: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                c = m.get("content", "")
                if isinstance(c, str):
                    system_parts.append(c)
            else:
                conv.append(m)
        return "\n\n".join(system_parts), conv

    @staticmethod
    def _wrap_delta(
        *,
        content: str | None = None,
        role: str | None = None,
        reasoning_content: str | None = None,
    ) -> dict:
        delta: dict = {}
        if content is not None:
            delta["content"] = content
        if role is not None:
            delta["role"] = role
        if reasoning_content is not None:
            delta["reasoning_content"] = reasoning_content
        return {
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            "usage": None,
        }
