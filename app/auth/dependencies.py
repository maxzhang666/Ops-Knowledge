import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.core.database import get_db
from app.department.service import DepartmentService

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    svc = AuthService(db)
    payload = svc.verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await svc.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    async def dependency(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return Depends(dependency)


async def check_resource_access(
    user: User,
    resource_type: str,
    resource_id: uuid.UUID,
    db: AsyncSession,
    created_by: uuid.UUID | None = None,
    required_level: str = "view",
) -> None:
    """Raise 403 if user has no access to the resource."""
    svc = DepartmentService(db)
    level = await svc.check_resource_access(
        user.id, user.role.value, resource_type, resource_id, created_by
    )
    if level is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this resource")

    priority = {"view": 1, "use": 2, "edit": 3, "full": 4}
    if priority.get(level, 0) < priority.get(required_level, 0):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient access level")
