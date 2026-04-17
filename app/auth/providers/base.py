"""BaseAuthProvider — pluggable authentication contract.

Implementations cover: local username/password, OIDC (Phase 1b),
SAML (Phase 3), LDAP (Phase 3). Each provider is responsible only
for *who the user is*; JWT issuance, revocation, and role enforcement
stay in AuthService.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User


@dataclass
class AuthResult:
    """Outcome of an authentication attempt.

    ``user`` present → authenticated. ``user`` None → failed; ``reason``
    may carry a human-readable detail for logging (never surfaced to the
    client verbatim to avoid user enumeration).
    """
    user: User | None
    reason: str | None = None


class BaseAuthProvider(ABC):
    """Provider plugin interface.

    Lifecycle:
      1. ``authenticate(db, credentials)`` — verify raw credentials and
         return the matching ``User`` (creating one on first SSO login if
         ``auto_provision`` is enabled).
      2. ``on_logout(user)`` — optional hook for provider-side logout
         (e.g. OIDC end-session endpoint). Default: no-op.

    Implementations must NOT issue JWT tokens; that's AuthService's job.
    """

    #: Short identifier stored in ``User.auth_provider``. Keep kebab-case
    #: (``"local"``, ``"oidc-keycloak"``, ``"saml-azure"``).
    name: str = "base"

    #: Whether first-time users authenticated by this provider should be
    #: auto-created in the local user table. SSO providers typically set True.
    auto_provision: bool = False

    @abstractmethod
    async def authenticate(
        self, db: AsyncSession, credentials: dict,
    ) -> AuthResult:
        """Validate credentials and return the authenticated user.

        ``credentials`` shape is provider-specific:
          - local: ``{"username": str, "password": str}``
          - oidc:  ``{"code": str, "state": str}``  (Phase 1b)
          - saml:  ``{"saml_response": str}``       (Phase 3)
        """

    async def on_logout(self, user: User) -> None:
        """Optional hook called on logout. Default is a no-op."""
        return None
