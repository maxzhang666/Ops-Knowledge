import uuid

from app.auth.models import UserRole
from app.auth.schemas import UserCreate
from app.auth.service import AuthService
from app.department.models import DepartmentRole
from app.department.schemas import DepartmentCreate
from app.department.service import DepartmentService


async def test_creator_has_full_access(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="creator", email="c@example.com", password="SecurePass123!"))
    resource_id = uuid.uuid4()
    access = await dept_svc.check_resource_access(user.id, UserRole.USER, "knowledge_base", resource_id, created_by=user.id)
    assert access == "full"


async def test_system_admin_has_full_access(db_session):
    dept_svc = DepartmentService(db_session)
    resource_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    access = await dept_svc.check_resource_access(admin_id, UserRole.SYSTEM_ADMIN, "knowledge_base", resource_id)
    assert access == "full"


async def test_dept_member_access_via_sharing(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    owner = await auth_svc.register(UserCreate(username="owner", email="o@example.com", password="SecurePass123!"))
    viewer = await auth_svc.register(UserCreate(username="viewer", email="v@example.com", password="SecurePass123!"))
    dept = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    await dept_svc.add_member(dept.id, viewer.id, DepartmentRole.VIEWER)
    resource_id = uuid.uuid4()
    await dept_svc.share_resource(dept.id, "knowledge_base", resource_id, "view", owner.id)
    access = await dept_svc.check_resource_access(viewer.id, UserRole.USER, "knowledge_base", resource_id)
    assert access == "view"


async def test_no_dept_no_access(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="lonely", email="l@example.com", password="SecurePass123!"))
    resource_id = uuid.uuid4()
    access = await dept_svc.check_resource_access(user.id, UserRole.USER, "knowledge_base", resource_id)
    assert access is None


async def test_subdept_inherits_parent_access(db_session):
    dept_svc = DepartmentService(db_session)
    auth_svc = AuthService(db_session)
    owner = await auth_svc.register(UserCreate(username="owner", email="o@example.com", password="SecurePass123!"))
    child_member = await auth_svc.register(UserCreate(username="child", email="c@example.com", password="SecurePass123!"))
    parent = await dept_svc.create_department(DepartmentCreate(name="Engineering"))
    child = await dept_svc.create_department(DepartmentCreate(name="Backend", parent_department_id=parent.id))
    await dept_svc.add_member(child.id, child_member.id, DepartmentRole.EDITOR)
    resource_id = uuid.uuid4()
    await dept_svc.share_resource(parent.id, "knowledge_base", resource_id, "edit", owner.id)
    access = await dept_svc.check_resource_access(child_member.id, UserRole.USER, "knowledge_base", resource_id)
    assert access == "edit"
