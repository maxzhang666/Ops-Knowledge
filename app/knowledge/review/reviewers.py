"""Plan 39 M2 — 候选审核员查询。

按 spec `19-ux-and-operations.md §14.2`：
    candidates = (dept_admin of any dept where KB shared)
                ∪ (system_admin)
                − (creator of unit)

KB 未共享给任何部门时仅 system_admin 可审。复用 dept_admin 角色，
不引入 KB 维度的审核人列表，保持权限模型简洁。
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.department.models import DepartmentResource, DepartmentRole, UserDepartment
from app.knowledge.models import KnowledgeBase


async def get_candidate_reviewers(
    db: AsyncSession,
    kb: KnowledgeBase,
    *,
    exclude_user_ids: set[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """Return list of user_ids who can review units in this KB.

    Args:
        db: async session
        kb: 目标 KB（需 created_by / id）
        exclude_user_ids: 排除集（一般是 unit creator —— 作者不能自审）
    """
    exclude = exclude_user_ids or set()
    candidates: set[uuid.UUID] = set()

    # 1. KB 共享到的部门集合（含 KB owner 自身的部门作为 fallback —— 即使
    #    没有显式 share，KB owner 部门的 dept_admin 也是合理审核员）
    shared_dept_ids: set[uuid.UUID] = set()
    rows = (await db.execute(
        select(DepartmentResource.department_id).where(
            DepartmentResource.resource_type == "knowledge_base",
            DepartmentResource.resource_id == kb.id,
        )
    )).scalars().all()
    shared_dept_ids.update(rows)

    # KB owner 自身的部门（spec: "shared depts ∪ owner's dept" 的语义保持兼容）
    owner_dept_rows = (await db.execute(
        select(UserDepartment.department_id).where(
            UserDepartment.user_id == kb.created_by,
        )
    )).scalars().all()
    shared_dept_ids.update(owner_dept_rows)

    # 2. dept_admin of those departments
    if shared_dept_ids:
        admin_rows = (await db.execute(
            select(UserDepartment.user_id).distinct().where(
                UserDepartment.department_id.in_(shared_dept_ids),
                UserDepartment.role == DepartmentRole.DEPT_ADMIN,
            )
        )).scalars().all()
        candidates.update(admin_rows)

    # 3. all system_admin
    system_admin_rows = (await db.execute(
        select(User.id).where(User.role == UserRole.SYSTEM_ADMIN)
    )).scalars().all()
    candidates.update(system_admin_rows)

    return [uid for uid in candidates if uid not in exclude]


async def is_user_reviewer_for_kb(
    db: AsyncSession,
    user: User,
    kb: KnowledgeBase,
) -> bool:
    """快速判断当前用户是否能审核此 KB 的 unit。
    用于 endpoint 权限校验。"""
    if user.role == UserRole.SYSTEM_ADMIN:
        return True
    candidates = await get_candidate_reviewers(db, kb)
    return user.id in candidates


async def kb_ids_user_can_review(
    db: AsyncSession,
    user: User,
) -> list[uuid.UUID] | None:
    """Return list of KB ids the user can review pending units in.
    None = system_admin（不限 KB 范围；调用方按 None 走全量查询）。"""
    if user.role == UserRole.SYSTEM_ADMIN:
        return None

    # 该用户是 dept_admin 的部门集合
    dept_ids = (await db.execute(
        select(UserDepartment.department_id).where(
            UserDepartment.user_id == user.id,
            UserDepartment.role == DepartmentRole.DEPT_ADMIN,
        )
    )).scalars().all()
    if not dept_ids:
        return []  # 不是任何部门的 admin，看不到

    # 这些部门共享到的 KB
    kb_ids_shared = (await db.execute(
        select(DepartmentResource.resource_id).distinct().where(
            DepartmentResource.resource_type == "knowledge_base",
            DepartmentResource.department_id.in_(dept_ids),
        )
    )).scalars().all()

    # 加上"owner 是同部门 dept_admin 的 KB"（owner_dept fallback）
    same_dept_users = (await db.execute(
        select(UserDepartment.user_id).distinct().where(
            UserDepartment.department_id.in_(dept_ids),
        )
    )).scalars().all()
    kb_ids_owned = (await db.execute(
        select(KnowledgeBase.id).where(
            KnowledgeBase.created_by.in_(same_dept_users),
        )
    )).scalars().all()

    return list({*kb_ids_shared, *kb_ids_owned})
