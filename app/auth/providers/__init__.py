"""Auth Provider plugin system.

Phase 1a delivers the pluggable interface only — one built-in provider
(``LocalProvider``). Future SSO providers (OIDC / SAML / LDAP) are
implemented in Phase 1b by subclassing ``BaseAuthProvider`` and
registering via ``AUTH_PROVIDERS``; no AuthService rewrite needed.

Selection rule:
  - ``settings.AUTH_PROVIDER`` string (default "local") picks the active
    provider at application start.
  - ``User.auth_provider`` column remembers which provider authenticated
    each user so future logins route back to the same one.
"""
from app.auth.providers.base import AuthResult, BaseAuthProvider
from app.auth.providers.local import LocalAuthProvider
from app.auth.providers.registry import (
    AUTH_PROVIDERS,
    get_active_provider,
    get_provider,
    register_provider,
)

__all__ = [
    "AuthResult",
    "BaseAuthProvider",
    "LocalAuthProvider",
    "AUTH_PROVIDERS",
    "get_active_provider",
    "get_provider",
    "register_provider",
]
