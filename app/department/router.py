import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.department.models import DepartmentRole, UserDepartment
from app.department.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentTreeResponse,
    DepartmentUpdate,
    MemberAssign,
    MemberResponse,
    MemberUpdate,
    ResourceShare,
    ResourceShareResponse,
)
from app.department.service import DepartmentService

router = APIRouter(prefix="/departments", tags=["departments"])


def _svc(db: AsyncSession) -> DepartmentService:
    return DepartmentService(db)


async def _require_dept_admin(
    dept_id: uuid.UUID, user: User, db: AsyncSession
) -> None:
    """Allow system_admin or dept_admin of the given department."""
    if user.role == UserRole.SYSTEM_ADMIN:
        return
    svc = DepartmentService(db)
    members = await svc.list_members(dept_id)
    for m in members:
        if m.user_id == user.id and m.role == DepartmentRole.DEPT_ADMIN:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


# --- Department CRUD ---

@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    dept = await _svc(db).create_department(data)
    return dept


@router.get("", response_model=list[DepartmentTreeResponse])
async def list_departments(
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return await _svc(db).get_department_tree()


@router.get("/{dept_id}", response_model=DepartmentResponse)
async def get_department(
    dept_id: uuid.UUID,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dept = await _svc(db).get_department(dept_id)
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    return dept


@router.post("/{dept_id}/update", response_model=DepartmentResponse)
async def update_department(
    dept_id: uuid.UUID,
    data: DepartmentUpdate,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).update_department(dept_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{dept_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    dept_id: uuid.UUID,
    _user: User = require_role(UserRole.SYSTEM_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    try:
        await _svc(db).delete_department(dept_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# --- Member Management ---

@router.get("/{dept_id}/members", response_model=list[MemberResponse])
async def list_members(
    dept_id: uuid.UUID,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, _user, db)
    members = await _svc(db).list_members(dept_id)
    return [
        MemberResponse(
            id=m.id,
            user_id=m.user_id,
            username=m.user.username,
            email=m.user.email,
            role=m.role,
            is_primary=m.is_primary,
        )
        for m in members
    ]


@router.post("/{dept_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    dept_id: uuid.UUID,
    data: MemberAssign,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, user, db)
    svc = _svc(db)
    member = await svc.add_member(dept_id, data.user_id, data.role, data.is_primary)
    # Reload with user relationship
    members = await svc.list_members(dept_id)
    m = next(m for m in members if m.user_id == data.user_id)
    return MemberResponse(
        id=m.id,
        user_id=m.user_id,
        username=m.user.username,
        email=m.user.email,
        role=m.role,
        is_primary=m.is_primary,
    )


@router.post("/{dept_id}/members/{user_id}/update", response_model=MemberResponse)
async def update_member_role(
    dept_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberUpdate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, user, db)
    svc = _svc(db)
    try:
        await svc.update_member_role(dept_id, user_id, data.role)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    members = await svc.list_members(dept_id)
    m = next(m for m in members if m.user_id == user_id)
    return MemberResponse(
        id=m.id,
        user_id=m.user_id,
        username=m.user.username,
        email=m.user.email,
        role=m.role,
        is_primary=m.is_primary,
    )


@router.post("/{dept_id}/members/{user_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    dept_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, user, db)
    await _svc(db).remove_member(dept_id, user_id)


# --- Resource Sharing ---

@router.post("/{dept_id}/resources", response_model=ResourceShareResponse, status_code=status.HTTP_201_CREATED)
async def share_resource(
    dept_id: uuid.UUID,
    data: ResourceShare,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, user, db)
    res = await _svc(db).share_resource(
        dept_id, data.resource_type, data.resource_id, data.access_level, user.id
    )
    return res


@router.post(
    "/{dept_id}/resources/{resource_type}/{resource_id}/unshare",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unshare_resource(
    dept_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _require_dept_admin(dept_id, user, db)
    await _svc(db).unshare_resource(dept_id, resource_type, resource_id)
