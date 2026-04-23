"""Workflow version history — list / get / rollback-to-draft."""
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import Workflow, WorkflowVersion


class VersionNotFound(Exception):
    pass


class VersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_versions(
        self, wf_id: uuid.UUID, *, page: int = 1, page_size: int = 20,
    ) -> list[WorkflowVersion]:
        rows = await self.db.execute(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == wf_id)
            .order_by(desc(WorkflowVersion.version))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all())

    async def get_version(self, wf_id: uuid.UUID, version: int) -> WorkflowVersion:
        row = await self.db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == wf_id,
                WorkflowVersion.version == version,
            )
        )
        v = row.scalar_one_or_none()
        if v is None:
            raise VersionNotFound(f"{wf_id}@{version}")
        return v

    async def rollback_to_draft(self, wf_id: uuid.UUID, version: int) -> Workflow:
        """Copy a historical version's graph into the draft slot. Does NOT
        auto-republish — user re-publishes explicitly to bump version."""
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise VersionNotFound(str(wf_id))
        v = await self.get_version(wf_id, version)
        wf.graph_data = dict(v.graph_data)
        wf.status = "draft"
        await self.db.flush()
        await self.db.refresh(wf)
        return wf
