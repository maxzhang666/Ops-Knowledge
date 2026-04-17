"""Auth provider registry — stable selection contract.

At application start each provider class registers itself here. ``AuthService``
resolves the active provider via ``get_active_provider()`` instead of
hard-coding concrete classes, so Phase 1b can add an OIDC provider by just
importing its module.
"""
from __future__ import annotations

from app.auth.providers.base import BaseAuthProvider
from app.auth.providers.local import LocalAuthProvider
from app.core.config import settings

AUTH_PROVIDERS: dict[str, BaseAuthProvider] = {}


def register_provider(provider: BaseAuthProvider) -> None:
    AUTH_PROVIDERS[provider.name] = provider


def get_provider(name: str) -> BaseAuthProvider | None:
    return AUTH_PROVIDERS.get(name)


def get_active_provider() -> BaseAuthProvider:
    """Return the provider selected by ``settings.AUTH_PROVIDER``.

    Falls back to ``local`` if the configured provider is missing
    (e.g. OIDC module not yet installed in Phase 1a).
    """
    name = getattr(settings, "AUTH_PROVIDER", "local")
    provider = AUTH_PROVIDERS.get(name)
    if provider is None:
        provider = AUTH_PROVIDERS["local"]
    return provider


# ── Built-ins (Phase 1a) ─────────────────────────────────────────
register_provider(LocalAuthProvider())
