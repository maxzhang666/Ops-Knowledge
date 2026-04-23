"""Workflow templates: save-as, create-from, list, delete."""
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import Workflow, WorkflowTemplate


class TemplateNotFound(Exception):
    pass


class TemplatesService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save_from_workflow(
        self,
        wf_id: uuid.UUID,
        user_id: uuid.UUID | None,
        *,
        name: str,
        description: str | None = None,
        category: str = "general",
    ) -> WorkflowTemplate:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise TemplateNotFound(str(wf_id))
        # Prefer the published snapshot; fall back to draft for never-published.
        source = wf.published_graph_data or wf.graph_data
        tpl = WorkflowTemplate(
            name=name,
            description=description,
            category=category,
            graph_data=dict(source or {}),
            is_builtin=False,
            created_by=user_id,
        )
        self.db.add(tpl)
        await self.db.flush()
        return tpl

    async def list_templates(
        self, *, category: str | None = None,
    ) -> list[WorkflowTemplate]:
        stmt = select(WorkflowTemplate).order_by(desc(WorkflowTemplate.created_at))
        if category:
            stmt = stmt.where(WorkflowTemplate.category == category)
        rows = await self.db.execute(stmt)
        return list(rows.scalars().all())

    async def get_template(self, tpl_id: uuid.UUID) -> WorkflowTemplate:
        tpl = await self.db.get(WorkflowTemplate, tpl_id)
        if tpl is None:
            raise TemplateNotFound(str(tpl_id))
        return tpl

    async def create_workflow_from_template(
        self, tpl_id: uuid.UUID, user_id: uuid.UUID | None, *, name: str,
    ) -> Workflow:
        tpl = await self.get_template(tpl_id)
        wf = Workflow(
            name=name,
            description=f"From template: {tpl.name}",
            graph_data=dict(tpl.graph_data),
            status="draft",
            created_by=user_id,
        )
        self.db.add(wf)
        await self.db.flush()
        await self.db.refresh(wf)
        return wf

    async def delete_template(self, tpl_id: uuid.UUID) -> None:
        tpl = await self.get_template(tpl_id)
        if tpl.is_builtin:
            raise ValueError("Cannot delete built-in template")
        await self.db.delete(tpl)
        await self.db.flush()

    async def duplicate_workflow(
        self, wf_id: uuid.UUID, user_id: uuid.UUID | None,
    ) -> Workflow:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise TemplateNotFound(str(wf_id))
        dup = Workflow(
            name=f"{wf.name} (副本)",
            description=wf.description,
            graph_data=dict(wf.graph_data),
            status="draft",
            created_by=user_id,
        )
        self.db.add(dup)
        await self.db.flush()
        await self.db.refresh(dup)
        return dup
