import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UserCreate
from app.core.config import settings

logger = structlog.get_logger(__name__)


def _redis_client():
    """Lazy Redis client; fail-open on any error."""
    try:
        import redis
        return redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
    except Exception:
        return None


def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Blacklist a single token by jti."""
    r = _redis_client()
    if r is None:
        return
    try:
        r.set(f"jwt:revoked_jti:{jti}", "1", ex=max(ttl_seconds, 1))
    except Exception:
        pass


def revoke_user_tokens(user_id: str) -> None:
    """Invalidate all tokens issued to a user before now."""
    r = _redis_client()
    if r is None:
        return
    try:
        ts = int(datetime.now(timezone.utc).timestamp())
        ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400 + 3600
        r.set(f"jwt:revoked_user:{user_id}", str(ts), ex=ttl)
    except Exception:
        pass


def _is_revoked(jti: str | None, user_id: str, iat: int | None) -> bool:
    r = _redis_client()
    if r is None:
        return False  # fail-open
    try:
        if jti and r.exists(f"jwt:revoked_jti:{jti}"):
            return True
        user_cutoff = r.get(f"jwt:revoked_user:{user_id}")
        if user_cutoff and iat is not None:
            cutoff_ts = int(user_cutoff.decode() if isinstance(user_cutoff, bytes) else user_cutoff)
            if iat < cutoff_ts:
                return True
    except Exception:
        return False
    return False


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserCreate) -> User:
        hashed = _hash_password(data.password)
        user = User(username=data.username, email=data.email, hashed_password=hashed)
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise ValueError("User with this username or email already exists")
        return user

    async def authenticate(self, username: str, password: str) -> User | None:
        """Local-credential login — routes through the active AuthProvider.

        Kept as a convenience wrapper so existing callers don't change. For
        SSO flows (Phase 1b+) call ``authenticate_via_provider()`` directly
        with provider-specific credentials.
        """
        return await self.authenticate_via_provider(
            "local", {"username": username, "password": password},
        )

    async def authenticate_via_provider(
        self, provider_name: str, credentials: dict,
    ) -> User | None:
        """Plugin-driven auth — dispatches to the named AuthProvider."""
        from app.auth.providers import get_provider
        provider = get_provider(provider_name)
        if provider is None:
            logger.warning("auth_provider_not_registered", name=provider_name)
            return None
        result = await provider.authenticate(self.db, credentials)
        if result.user is None:
            logger.info(
                "auth_failed", provider=provider_name, reason=result.reason,
            )
        return result.user

    def create_tokens(self, user: User) -> dict[str, str]:
        access = self._create_token(
            {"sub": str(user.id), "role": user.role.value},
            timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh = self._create_token(
            {"sub": str(user.id), "type": "refresh"},
            timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    def verify_token(self, token: str) -> dict | None:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return None
        # Revocation check
        user_id = str(payload.get("sub") or "")
        if user_id and _is_revoked(payload.get("jti"), user_id, payload.get("iat")):
            return None
        return payload

    async def get_user_by_id(self, user_id: str) -> User | None:
        stmt = select(User).where(User.id == uuid.UUID(user_id), User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _create_token(self, data: dict, expires_delta: timedelta) -> str:
        now = datetime.now(timezone.utc)
        to_encode = data.copy()
        to_encode["exp"] = now + expires_delta
        to_encode["iat"] = int(now.timestamp())
        to_encode["jti"] = uuid.uuid4().hex
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
