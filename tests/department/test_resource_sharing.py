import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models import UserRole
from app.auth.schemas import UserCreate
from app.auth.service import AuthService
from app.department.schemas import DepartmentCreate
from app.department.service import DepartmentService


async def test_share_resource(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="admin", email="admin@example.com", password="SecurePass123!"))
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    resource_id = uuid.uuid4()
    share = await dept_svc.share_resource(dept.id, "knowledge_base", resource_id, "edit", user.id)
    assert share.access_level == "edit"


async def test_share_duplicate_fails(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="admin", email="admin@example.com", password="SecurePass123!"))
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    resource_id = uuid.uuid4()
    await dept_svc.share_resource(dept.id, "knowledge_base", resource_id, "edit", user.id)
    with pytest.raises(IntegrityError):
        await dept_svc.share_resource(dept.id, "knowledge_base", resource_id, "view", user.id)


async def test_unshare_resource(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="admin", email="admin@example.com", password="SecurePass123!"))
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    resource_id = uuid.uuid4()
    await dept_svc.share_resource(dept.id, "knowledge_base", resource_id, "edit", user.id)
    await dept_svc.unshare_resource(dept.id, "knowledge_base", resource_id)
    access = await dept_svc.check_resource_access(user.id, UserRole.USER, "knowledge_base", resource_id)
    assert access is None
