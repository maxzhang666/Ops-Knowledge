import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UserCreate
from app.core.config import settings


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
        stmt = select(User).where(User.username == username, User.is_active.is_(True))
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None or not _verify_password(password, user.hashed_password):
            return None
        return user

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
            return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return None

    async def get_user_by_id(self, user_id: str) -> User | None:
        stmt = select(User).where(User.id == uuid.UUID(user_id), User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _create_token(self, data: dict, expires_delta: timedelta) -> str:
        to_encode = data.copy()
        to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
