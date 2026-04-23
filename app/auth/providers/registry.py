"""Auth provider registry — stable selection contract.

At application start each provider class registers itself here. ``AuthService``
dispatches per-request via ``get_provider(name)``: local for password login,
``oidc`` for the SSO router. OIDC configuration (issuer / client_id / secret)
is stored in ``SystemSettings.settings['sso']`` and edited through the UI.
"""
from __future__ import annotations

from app.auth.providers.base import BaseAuthProvider
from app.auth.providers.local import LocalAuthProvider

AUTH_PROVIDERS: dict[str, BaseAuthProvider] = {}


def register_provider(provider: BaseAuthProvider) -> None:
    AUTH_PROVIDERS[provider.name] = provider


def get_provider(name: str) -> BaseAuthProvider | None:
    return AUTH_PROVIDERS.get(name)


# ── Built-ins (Phase 1a) ─────────────────────────────────────────
register_provider(LocalAuthProvider())

# ── Phase 1b additions ───────────────────────────────────────────
from app.auth.providers.oidc import OIDCAuthProvider  # noqa: E402
register_provider(OIDCAuthProvider())
