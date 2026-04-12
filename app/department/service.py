import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import UserRole
from app.department.models import Department, DepartmentResource, DepartmentRole, UserDepartment
from app.department.schemas import DepartmentCreate, DepartmentTreeResponse, DepartmentUpdate


class DepartmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Department CRUD ---

    async def create_department(self, data: DepartmentCreate) -> Department:
        dept = Department(
            name=data.name,
            description=data.description,
            parent_department_id=data.parent_department_id,
        )
        self.db.add(dept)
        await self.db.flush()
        return dept

    async def get_department(self, dept_id: uuid.UUID) -> Department | None:
        return await self.db.get(Department, dept_id)

    async def update_department(self, dept_id: uuid.UUID, data: DepartmentUpdate) -> Department:
        dept = await self.db.get(Department, dept_id)
        if dept is None:
            raise ValueError("Department not found")
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(dept, k, v)
        await self.db.flush()
        return dept

    async def delete_department(self, dept_id: uuid.UUID) -> None:
        dept = await self.db.get(Department, dept_id)
        if dept is None:
            raise ValueError("Department not found")
        # Check for child departments
        children = await self.db.scalars(
            select(Department).where(Department.parent_department_id == dept_id)
        )
        if children.first() is not None:
            raise ValueError("Cannot delete department with child departments")
        await self.db.delete(dept)
        await self.db.flush()

    async def get_department_tree(self) -> list[DepartmentTreeResponse]:
        result = await self.db.scalars(select(Department).order_by(Department.name))
        all_depts = result.all()

        dept_map: dict[uuid.UUID, DepartmentTreeResponse] = {}
        for d in all_depts:
            dept_map[d.id] = DepartmentTreeResponse.model_validate(d)

        roots: list[DepartmentTreeResponse] = []
        for d in dept_map.values():
            if d.parent_department_id and d.parent_department_id in dept_map:
                dept_map[d.parent_department_id].children.append(d)
            else:
                roots.append(d)
        return roots

    # --- Member Management ---

    async def add_member(
        self,
        dept_id: uuid.UUID,
        user_id: uuid.UUID,
        role: DepartmentRole = DepartmentRole.VIEWER,
        is_primary: bool = False,
    ) -> UserDepartment:
        member = UserDepartment(
            department_id=dept_id, user_id=user_id, role=role, is_primary=is_primary
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def remove_member(self, dept_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(UserDepartment).where(
                UserDepartment.department_id == dept_id,
                UserDepartment.user_id == user_id,
            )
        )
        await self.db.flush()

    async def update_member_role(
        self, dept_id: uuid.UUID, user_id: uuid.UUID, role: DepartmentRole
    ) -> UserDepartment:
        result = await self.db.scalars(
            select(UserDepartment).where(
                UserDepartment.department_id == dept_id,
                UserDepartment.user_id == user_id,
            )
        )
        member = result.first()
        if member is None:
            raise ValueError("Member not found")
        member.role = role
        await self.db.flush()
        return member

    async def list_members(self, dept_id: uuid.UUID) -> list[UserDepartment]:
        result = await self.db.scalars(
            select(UserDepartment)
            .options(selectinload(UserDepartment.user))
            .where(UserDepartment.department_id == dept_id)
        )
        return list(result.all())

    # --- Resource Sharing ---

    async def share_resource(
        self,
        dept_id: uuid.UUID,
        resource_type: str,
        resource_id: uuid.UUID,
        access_level: str,
        shared_by: uuid.UUID,
    ) -> DepartmentResource:
        res = DepartmentResource(
            department_id=dept_id,
            resource_type=resource_type,
            resource_id=resource_id,
            access_level=access_level,
            shared_by=shared_by,
        )
        self.db.add(res)
        await self.db.flush()
        return res

    async def unshare_resource(
        self, dept_id: uuid.UUID, resource_type: str, resource_id: uuid.UUID
    ) -> None:
        await self.db.execute(
            delete(DepartmentResource).where(
                DepartmentResource.department_id == dept_id,
                DepartmentResource.resource_type == resource_type,
                DepartmentResource.resource_id == resource_id,
            )
        )
        await self.db.flush()

    # --- Access Control ---

    async def get_user_department_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.db.scalars(
            select(UserDepartment.department_id).where(UserDepartment.user_id == user_id)
        )
        return list(result.all())

    async def get_ancestor_department_ids(self, dept_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        """Recursively traverse upward to collect all ancestor department IDs."""
        all_ids: set[uuid.UUID] = set(dept_ids)
        pending = list(dept_ids)

        while pending:
            result = await self.db.scalars(
                select(Department.parent_department_id).where(
                    Department.id.in_(pending),
                    Department.parent_department_id.isnot(None),
                )
            )
            parents = [pid for pid in result.all() if pid not in all_ids]
            all_ids.update(parents)
            pending = parents

        return list(all_ids)

    async def check_resource_access(
        self,
        user_id: uuid.UUID,
        user_role: UserRole,
        resource_type: str,
        resource_id: uuid.UUID,
        created_by: uuid.UUID | None = None,
    ) -> str | None:
        """Return highest access level: 'full'/'view'/'edit'/'use' or None."""
        if user_role == UserRole.SYSTEM_ADMIN:
            return "full"
        if created_by and created_by == user_id:
            return "full"

        dept_ids = await self.get_user_department_ids(user_id)
        if not dept_ids:
            return None
        all_dept_ids = await self.get_ancestor_department_ids(dept_ids)

        result = await self.db.scalars(
            select(DepartmentResource.access_level).where(
                DepartmentResource.department_id.in_(all_dept_ids),
                DepartmentResource.resource_type == resource_type,
                DepartmentResource.resource_id == resource_id,
            )
        )
        levels = set(result.all())
        if not levels:
            return None

        priority = ["full", "edit", "use", "view"]
        for lvl in priority:
            if lvl in levels:
                return lvl
        return None

    async def get_accessible_resource_ids(
        self, user_id: uuid.UUID, resource_type: str
    ) -> list[uuid.UUID]:
        dept_ids = await self.get_user_department_ids(user_id)
        if not dept_ids:
            return []
        all_dept_ids = await self.get_ancestor_department_ids(dept_ids)

        result = await self.db.scalars(
            select(DepartmentResource.resource_id).where(
                DepartmentResource.department_id.in_(all_dept_ids),
                DepartmentResource.resource_type == resource_type,
            )
        )
        return list(result.all())
