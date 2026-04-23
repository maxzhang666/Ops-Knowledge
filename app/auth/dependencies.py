import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.core.database import get_db
from app.department.service import DepartmentService

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_api_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # API key authentication
    if x_api_key:
        from app.system.service import ApiKeyService
        api_svc = ApiKeyService(db)
        api_key = await api_svc.verify_key(x_api_key)
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        request.state.api_key_scope = api_key.scope
        auth_svc = AuthService(db)
        user = await auth_svc.get_user_by_id(str(api_key.user_id))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    # JWT Bearer authentication
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

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


async def authenticate_ws_token(token: str | None, db: AsyncSession) -> User:
    """WebSocket helper — can't use HTTPBearer / Depends chain. Browsers can't
    attach Authorization headers to WS, so clients pass the JWT via `?token=`.
    Raises on any issue; the caller translates to a WS close with 4401."""
    if not token:
        raise ValueError("missing token")
    svc = AuthService(db)
    payload = svc.verify_token(token)
    if payload is None:
        raise ValueError("invalid token")
    sub = payload.get("sub")
    if not sub:
        raise ValueError("invalid token (no sub)")
    user = await svc.get_user_by_id(sub)
    if user is None:
        raise ValueError("user not found or inactive")
    return user
