from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User, UserRole
from app.auth.schemas import TokenRefresh, TokenResponse, UserCreate, UserLogin, UserResponse
from app.auth.service import AuthService
from app.core.database import get_db
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_caller(request: Request, db: AsyncSession) -> User | None:
    """Extract authenticated user from request without requiring auth."""
    auth_header = request.headers.get("authorization", "")
    api_key_header = request.headers.get("x-api-key")

    if api_key_header:
        from app.system.service import ApiKeyService
        api_svc = ApiKeyService(db)
        api_key = await api_svc.verify_key(api_key_header)
        if api_key is None:
            return None
        svc = AuthService(db)
        return await svc.get_user_by_id(str(api_key.user_id))

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        svc = AuthService(db)
        payload = svc.verify_token(token)
        if payload and payload.get("sub"):
            return await svc.get_user_by_id(payload["sub"])
    return None


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    if user_count > 0:
        caller = await _get_caller(request, db)
        if caller is None or caller.role != UserRole.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only system_admin can register new users after initialization",
            )

    svc = AuthService(db)
    try:
        user = await svc.register(data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    user = await svc.authenticate(data.username, data.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return svc.create_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    payload = svc.verify_token(data.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = await svc.get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return svc.create_tokens(user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=72)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.auth.service import _verify_password, _hash_password, revoke_user_tokens
    if not _verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = _hash_password(data.new_password)
    await db.flush()
    await db.commit()
    # Revoke all existing tokens of this user — forces re-login on other sessions
    revoke_user_tokens(str(current_user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current access token by its jti."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return  # API key auth — logout is a no-op
    token = auth_header[7:]
    svc = AuthService(db)
    payload = svc.verify_token(token)
    if payload is None:
        return
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    import time as _time
    from app.auth.service import revoke_jti
    ttl = max(int(exp) - int(_time.time()), 1)
    revoke_jti(jti, ttl)
