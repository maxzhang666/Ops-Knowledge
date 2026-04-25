"""KB Notify Owner node (Plan 27 M5).

发送治理通知到文档 / KB / 用户。可用于 stale 文档 / knowledge_gap 派单。

Input:
  * user_id (UUID string, optional)           —— 指定接收人；缺省时结合 resource_id 自动派发
  * resource_type ("document" | "kb")         —— 可选
  * resource_id (UUID string, optional)       —— 目标 document 或 kb 的 id；用于补充 owner 和 dept_admin
  * title (str) —— 必填
  * content (str)

Output:
  * notified_user_ids: list[str]
"""
from __future__ import annotations

import uuid

from app.workflow.nodes.base import (
    AbstractNode, NodeConfigForm, NodeContext, NodeIO, NodeManifest, NodeResult,
)


class KBNotifyOwnerNode(AbstractNode):
    manifest = NodeManifest(
        type="kb_notify_owner",
        category="extension",
        name="通知责任人",
        description="创建 Notification 通知文档创建者 + 部门 dept_admin（治理 Workflow 动作节点）",
    )
    io = NodeIO(
        inputs={
            "user_id": {"type": "string"},
            "resource_type": {"type": "string"},
            "resource_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
        },
        outputs={"notified_user_ids": {"type": "array"}},
    )
    config_form = NodeConfigForm(schema={
        "type": "object",
        "properties": {
            "priority": {"type": "string", "default": "normal"},
            "type": {"type": "string", "default": "governance"},
        },
    })

    async def validate(self, ctx: NodeContext) -> None:
        title = ctx.inputs.get("title") or ctx.config.get("title")
        if not title:
            raise ValueError("kb_notify_owner: 'title' input or config is required")

    async def execute(self, ctx: NodeContext) -> NodeResult:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.department.models import DepartmentRole, UserDepartment
        from app.knowledge.models import Document, KnowledgeBase
        from app.system.models import Notification

        title = str(ctx.inputs.get("title") or ctx.config.get("title"))
        content = str(ctx.inputs.get("content") or ctx.config.get("content") or "")
        priority = str(ctx.config.get("priority") or "normal")
        notif_type = str(ctx.config.get("type") or "governance")

        user_id_raw = ctx.inputs.get("user_id")
        resource_type = ctx.inputs.get("resource_type")
        resource_id_raw = ctx.inputs.get("resource_id")

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sm() as db:
                targets: set[uuid.UUID] = set()
                if user_id_raw:
                    try:
                        targets.add(uuid.UUID(str(user_id_raw)))
                    except ValueError:
                        pass

                owner_id: uuid.UUID | None = None
                if resource_type == "document" and resource_id_raw:
                    doc = await db.get(Document, uuid.UUID(str(resource_id_raw)))
                    if doc:
                        owner_id = doc.created_by
                elif resource_type == "kb" and resource_id_raw:
                    kb = await db.get(KnowledgeBase, uuid.UUID(str(resource_id_raw)))
                    if kb:
                        owner_id = kb.created_by

                if owner_id:
                    targets.add(owner_id)
                    # dept admins 加入
                    dept_ids = (await db.execute(
                        select(UserDepartment.department_id).where(
                            UserDepartment.user_id == owner_id,
                        )
                    )).scalars().all()
                    if dept_ids:
                        admin_rows = (await db.execute(
                            select(UserDepartment.user_id).distinct().where(
                                UserDepartment.department_id.in_(dept_ids),
                                UserDepartment.role == DepartmentRole.DEPT_ADMIN,
                            )
                        )).scalars().all()
                        for u in admin_rows:
                            if u != owner_id:
                                targets.add(u)

                notified: list[str] = []
                for uid in targets:
                    db.add(Notification(
                        user_id=uid,
                        type=notif_type,
                        title=title,
                        content=content,
                        priority=priority,
                        resource_type=str(resource_type) if resource_type else None,
                        resource_id=uuid.UUID(str(resource_id_raw)) if resource_id_raw else None,
                    ))
                    notified.append(str(uid))
                await db.commit()
                return NodeResult(outputs={"notified_user_ids": notified})
        finally:
            await engine.dispose()
