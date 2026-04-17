"""Local username + password provider."""
from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.providers.base import AuthResult, BaseAuthProvider


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class LocalAuthProvider(BaseAuthProvider):
    """Username + bcrypt password (the Phase 1a default)."""

    name = "local"
    auto_provision = False

    async def authenticate(self, db: AsyncSession, credentials: dict) -> AuthResult:
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            return AuthResult(user=None, reason="missing_credentials")

        stmt = select(User).where(User.username == username, User.is_active.is_(True))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return AuthResult(user=None, reason="user_not_found")
        if not user.hashed_password:
            # Users provisioned via SSO don't have a local password — refuse
            # to accept local login for them.
            return AuthResult(user=None, reason="no_local_password")
        if not _verify_password(password, user.hashed_password):
            return AuthResult(user=None, reason="bad_password")
        return AuthResult(user=user)
