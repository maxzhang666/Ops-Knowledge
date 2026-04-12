"""Department CRUD tests (DB-dependent, require running PostgreSQL)."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.department.models import DepartmentRole
from app.department.schemas import DepartmentCreate, DepartmentUpdate
from app.department.service import DepartmentService


@pytest.fixture
def svc(db_session: AsyncSession) -> DepartmentService:
    return DepartmentService(db_session)


@pytest.mark.asyncio
async def test_create_department(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Engineering"))
    assert dept.id is not None
    assert dept.name == "Engineering"


@pytest.mark.asyncio
async def test_get_department(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Sales"))
    found = await svc.get_department(dept.id)
    assert found is not None
    assert found.name == "Sales"


@pytest.mark.asyncio
async def test_update_department(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Old"))
    updated = await svc.update_department(dept.id, DepartmentUpdate(name="New"))
    assert updated.name == "New"


@pytest.mark.asyncio
async def test_delete_department(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Temp"))
    await svc.delete_department(dept.id)
    assert await svc.get_department(dept.id) is None


@pytest.mark.asyncio
async def test_delete_department_with_children_fails(svc: DepartmentService):
    parent = await svc.create_department(DepartmentCreate(name="Parent"))
    await svc.create_department(DepartmentCreate(name="Child", parent_department_id=parent.id))
    with pytest.raises(ValueError, match="child departments"):
        await svc.delete_department(parent.id)


@pytest.mark.asyncio
async def test_department_tree(svc: DepartmentService):
    parent = await svc.create_department(DepartmentCreate(name="Root"))
    await svc.create_department(DepartmentCreate(name="Child", parent_department_id=parent.id))
    tree = await svc.get_department_tree()
    assert len(tree) >= 1
    root = next(t for t in tree if t.name == "Root")
    assert len(root.children) == 1


@pytest.mark.asyncio
async def test_add_and_list_members(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Team"))
    user_id = uuid.uuid4()
    member = await svc.add_member(dept.id, user_id, DepartmentRole.EDITOR)
    assert member.role == DepartmentRole.EDITOR

    members = await svc.list_members(dept.id)
    assert len(members) == 1


@pytest.mark.asyncio
async def test_share_and_unshare_resource(svc: DepartmentService):
    dept = await svc.create_department(DepartmentCreate(name="Res"))
    rid = uuid.uuid4()
    shared = await svc.share_resource(dept.id, "knowledge_base", rid, "view", uuid.uuid4())
    assert shared.access_level == "view"

    await svc.unshare_resource(dept.id, "knowledge_base", rid)
