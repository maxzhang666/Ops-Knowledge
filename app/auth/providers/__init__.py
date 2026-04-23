"""Auth Provider plugin system.

Adding a new provider = subclass ``BaseAuthProvider`` + call
``register_provider(MyProvider())`` from within ``registry.py``. No
AuthService rewrite needed.

Routing rule:
  - ``/auth/login`` always uses the ``local`` provider (password login).
  - ``/auth/sso/*`` routes to the ``oidc`` provider; its config lives in
    ``SystemSettings.settings['sso']`` and is edited via UI.
  - ``User.auth_provider`` column remembers which provider authenticated
    each user so future logins route back to the same one.
"""
from app.auth.providers.base import AuthResult, BaseAuthProvider
from app.auth.providers.local import LocalAuthProvider
from app.auth.providers.registry import (
    AUTH_PROVIDERS,
    get_provider,
    register_provider,
)

__all__ = [
    "AuthResult",
    "BaseAuthProvider",
    "LocalAuthProvider",
    "AUTH_PROVIDERS",
    "get_provider",
    "register_provider",
]
