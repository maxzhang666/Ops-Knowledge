"""Provider plugin registry.

Register implementations by importing them at the bottom of this file.
``get_provider_impl(type_)`` returns a Provider instance, defaulting to
``OpenAICompatProvider`` for unknown types.
"""
from __future__ import annotations

from app.model.providers.base import BaseProvider, FieldSchema

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {}


def register_provider(cls: type[BaseProvider]) -> type[BaseProvider]:
    """Class decorator: map each supported_types() entry → cls."""
    for t in cls.supported_types():
        if t in PROVIDER_REGISTRY:
            raise RuntimeError(
                f"Provider type '{t}' already registered by "
                f"{PROVIDER_REGISTRY[t].__name__}; cannot re-register with {cls.__name__}"
            )
        PROVIDER_REGISTRY[t] = cls
    return cls


def get_provider_impl(type_: str) -> BaseProvider:
    """Instantiate the Provider for ``type_``. Unknown → OpenAICompatProvider."""
    cls = PROVIDER_REGISTRY.get(type_)
    if cls is None:
        cls = _default_fallback()
    return cls()


def _default_fallback() -> type[BaseProvider]:
    from app.model.providers.openai_compat import OpenAICompatProvider
    return OpenAICompatProvider


def list_provider_schemas() -> list[dict]:
    """Return schema for ``GET /model/provider-types``.

    De-duplicate classes that register multiple types so each type surfaces
    its own label/fields/capabilities entry.
    """
    out: list[dict] = []
    for type_, cls in PROVIDER_REGISTRY.items():
        out.append({
            "type": type_,
            "label": cls.display_label(type_),
            "fields": cls.required_fields(type_),
            "capabilities": cls.capabilities(),
        })
    out.sort(key=lambda x: x["label"])
    return out


# ── Auto-register Provider implementations ──
# Order matters only for deterministic registry contents at import time.
from app.model.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from app.model.providers.anthropic import AnthropicProvider  # noqa: E402
from app.model.providers.azure import AzureProvider  # noqa: E402
from app.model.providers.litellm_fallback import LiteLLMFallbackProvider  # noqa: E402

__all__ = [
    "BaseProvider",
    "FieldSchema",
    "PROVIDER_REGISTRY",
    "register_provider",
    "get_provider_impl",
    "list_provider_schemas",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "AzureProvider",
    "LiteLLMFallbackProvider",
]
