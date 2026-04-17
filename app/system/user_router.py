import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import User, UserRole
from app.auth.schemas import UserResponse
from app.auth.service import _hash_password
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.department.service import DepartmentService

router = APIRouter(prefix="/system/users", tags=["users"])


class UserCreateAdmin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    role: UserRole = UserRole.USER


class UserUpdateAdmin(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None


@router.get("", response_model=PaginatedResponse)
async def list_users(
    department_id: uuid.UUID | None = None,
    pagination: PaginationParams = Depends(),
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    base = select(User)

    if department_id:
        from app.department.models import UserDepartment
        base = base.join(UserDepartment, UserDepartment.user_id == User.id).where(
            UserDepartment.department_id == department_id
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    rows = await db.scalars(
        base.order_by(User.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    )
    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in rows.all()],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreateAdmin,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=_hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    return user


@router.post("/{user_id}/update", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateAdmin,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    updates = data.model_dump(exclude_unset=True)
    was_active = user.is_active
    for k, v in updates.items():
        setattr(user, k, v)
    await db.flush()
    # If deactivated, revoke all existing tokens
    if was_active and updates.get("is_active") is False:
        from app.auth.service import revoke_user_tokens
        revoke_user_tokens(str(user.id))
    return user


@router.post("/{user_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Protect last admin
    admin_count = (await db.execute(
        select(func.count()).where(User.role == UserRole.SYSTEM_ADMIN, User.is_active.is_(True))
    )).scalar() or 0

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == UserRole.SYSTEM_ADMIN and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last system admin")

    user.is_active = False
    await db.flush()
    # Revoke all tokens of the soft-deleted user
    from app.auth.service import revoke_user_tokens
    revoke_user_tokens(str(user.id))
