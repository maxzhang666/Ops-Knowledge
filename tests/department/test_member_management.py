import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import UserCreate
from app.auth.service import AuthService
from app.department.models import DepartmentRole
from app.department.schemas import DepartmentCreate
from app.department.service import DepartmentService


async def _create_user(db_session, username="testuser"):
    svc = AuthService(db_session)
    return await svc.register(UserCreate(
        username=username, email=f"{username}@example.com", password="SecurePass123!"
    ))


async def test_add_member(db_session):
    dept_svc = DepartmentService(db_session)
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    user = await _create_user(db_session)
    member = await dept_svc.add_member(dept.id, user.id, DepartmentRole.EDITOR)
    assert member.role == DepartmentRole.EDITOR
    assert member.is_primary is False


async def test_add_duplicate_member_fails(db_session):
    dept_svc = DepartmentService(db_session)
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    user = await _create_user(db_session)
    await dept_svc.add_member(dept.id, user.id)
    with pytest.raises(IntegrityError):
        await dept_svc.add_member(dept.id, user.id)


async def test_update_member_role(db_session):
    dept_svc = DepartmentService(db_session)
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    user = await _create_user(db_session)
    await dept_svc.add_member(dept.id, user.id, DepartmentRole.VIEWER)
    updated = await dept_svc.update_member_role(dept.id, user.id, DepartmentRole.DEPT_ADMIN)
    assert updated.role == DepartmentRole.DEPT_ADMIN


async def test_remove_member(db_session):
    dept_svc = DepartmentService(db_session)
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    user = await _create_user(db_session)
    await dept_svc.add_member(dept.id, user.id)
    await dept_svc.remove_member(dept.id, user.id)
    members = await dept_svc.list_members(dept.id)
    assert len(members) == 0
