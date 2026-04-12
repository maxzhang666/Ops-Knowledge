import hashlib
import json
import secrets
import uuid
from pathlib import Path

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.system.models import ApiKey, Notification, SystemSettings
from app.system.schemas import ApiKeyCreate

logger = structlog.get_logger(__name__)

SEED_DIR = Path(__file__).resolve().parent.parent / "core" / "seed"


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


class InitService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def needs_init(self) -> bool:
        from app.auth.models import User
        count = (await self.db.execute(select(func.count()).select_from(User))).scalar() or 0
        return count == 0

    async def initialize(self, username: str, email: str, password: str):
        from app.auth.models import User, UserRole
        from app.auth.service import AuthService

        if not await self.needs_init():
            raise ValueError("System already initialized")

        auth_svc = AuthService(self.db)
        from app.auth.schemas import UserCreate
        user = await auth_svc.register(UserCreate(username=username, email=email, password=password))
        user.role = UserRole.SYSTEM_ADMIN
        await self.db.flush()

        await self._load_seed_data(user.id)

        logger.info("system_initialized", admin=username)
        return user

    async def _load_seed_data(self, admin_id: uuid.UUID) -> None:
        seed_data: dict = {}
        for name in ("retrieval_presets", "prompt_templates", "model_pricing", "chunking_presets"):
            path = SEED_DIR / f"{name}.json"
            if path.exists():
                seed_data[name] = json.loads(path.read_text(encoding="utf-8"))

        ss = SystemSettings(id=1, settings=seed_data, updated_by=admin_id)
        self.db.add(ss)
        await self.db.flush()


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send(
        self,
        user_id: uuid.UUID,
        type: str,
        title: str,
        content: str | None = None,
        priority: str = "normal",
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            content=content,
            priority=priority,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        is_read: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        if is_read is not None:
            stmt = stmt.where(Notification.is_read == is_read)
        stmt = stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        return (await self.db.execute(stmt)).scalar() or 0

    async def mark_read(self, notif_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Notification).where(Notification.id == notif_id).values(is_read=True)
        )

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
