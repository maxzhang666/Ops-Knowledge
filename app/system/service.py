import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.system.models import ApiKey
from app.system.schemas import ApiKeyCreate


class ApiKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(self, user_id: uuid.UUID, data: ApiKeyCreate) -> tuple[ApiKey, str]:
        raw_key = f"sk-{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]

        api_key = ApiKey(
            user_id=user_id,
            name=data.name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scope=data.scope,
            expires_at=data.expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()
        return api_key, raw_key

    async def verify_key(self, raw_key: str) -> ApiKey | None:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        result = await self.db.execute(stmt)
        api_key = result.scalar_one_or_none()
        if api_key is None:
            return None
        if api_key.expires_at is not None:
            from datetime import datetime, timezone
            if api_key.expires_at < datetime.now(timezone.utc):
                return None
        return api_key

    async def list_keys(self, user_id: uuid.UUID) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def revoke_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> None:
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        result = await self.db.execute(stmt)
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise ValueError("API key not found")
        api_key.is_active = False
        await self.db.flush()
