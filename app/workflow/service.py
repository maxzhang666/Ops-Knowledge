"""Workflow service: DB access + DSL validation. Router stays thin."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.dsl import DSLValidationError, parse_dsl, parse_dsl_loose
from app.workflow.models import Workflow, WorkflowVersion
from app.workflow.schemas import WorkflowCreate, WorkflowUpdate


# Every Workflow must have a Start node — publish validation mandates it.
# We seed it at create time so any API client (Workflow Agent auto-provision,
# Orchestrator SOP list, direct REST call) gets a usable canvas. Authors add
# / replace nodes from there.
_DEFAULT_SEED_GRAPH = {
    "dsl_version": "1.0",
    "graph": {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 80, "y": 120}, "data": {}},
        ],
        "edges": [],
    },
    "workflow_variables": [],
}


def _has_any_node(graph_data: dict | None) -> bool:
    if not graph_data:
        return False
    graph = graph_data.get("graph") or {}
    nodes = graph.get("nodes")
    return isinstance(nodes, list) and len(nodes) > 0


class WorkflowNotFound(Exception):
    pass


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        data: WorkflowCreate,
        user_id: uuid.UUID | None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> Workflow:
        # Shape-only validation — drafts can be structurally incomplete.
        parse_dsl_loose(data.graph_data)
        # Every Workflow must have a Start node. If the client didn't supply
        # any nodes, seed Start so the canvas is immediately editable and
        # publish won't fail with "missing Start".
        graph_data = data.graph_data
        if not _has_any_node(graph_data):
            graph_data = _DEFAULT_SEED_GRAPH
        wf = Workflow(
            name=data.name,
            description=data.description,
            trigger_type=data.trigger_type,
            graph_data=graph_data,
            owner_agent_id=owner_agent_id,
            created_by=user_id,
        )
        self.db.add(wf)
        await self.db.flush()
        # Load server-generated created_at / updated_at so FastAPI response
        # serialization doesn't lazy-load out of async session context.
        await self.db.refresh(wf)
        return wf

    async def get(self, wf_id: uuid.UUID) -> Workflow:
        wf = await self.db.get(Workflow, wf_id)
        if wf is None:
            raise WorkflowNotFound(str(wf_id))
        return wf

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        owner_agent_id: uuid.UUID | None = None,
        trigger_type: str | None = None,
        status: str | None = None,
    ) -> list[Workflow]:
        stmt = select(Workflow).order_by(desc(Workflow.updated_at))
        if owner_agent_id is not None:
            stmt = stmt.where(Workflow.owner_agent_id == owner_agent_id)
        if trigger_type is not None:
            stmt = stmt.where(Workflow.trigger_type == trigger_type)
        if status is not None:
            stmt = stmt.where(Workflow.status == status)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = await self.db.execute(stmt)
        return list(rows.scalars().all())

    async def update(self, wf_id: uuid.UUID, data: WorkflowUpdate) -> Workflow:
        wf = await self.get(wf_id)
        if data.graph_data is not None:
            # Shape-only — drafts are saved incrementally; publish does the
            # strict structural pass (Start required, acyclic, refs valid).
            parse_dsl_loose(data.graph_data)
            wf.graph_data = data.graph_data
        if data.name is not None:
            wf.name = data.name
        if data.description is not None:
            wf.description = data.description
        await self.db.flush()
        # Reload updated_at (server-side onupdate) before returning — without
        # this FastAPI serialization triggers a lazy-load outside the async
        # session context and blows up with MissingGreenlet.
        await self.db.refresh(wf)
        return wf

    async def delete(self, wf_id: uuid.UUID) -> None:
        wf = await self.get(wf_id)
        await self.db.delete(wf)
        await self.db.flush()

    async def publish(
        self, wf_id: uuid.UUID, user_id: uuid.UUID | None, change_note: str | None = None
    ) -> Workflow:
        wf = await self.get(wf_id)
        # Validate before promoting. Reject empty/near-empty graphs — a
        # published workflow must be runnable (Start + at least one other node).
        dsl = parse_dsl(wf.graph_data)
        if len(dsl.graph.nodes) < 2:
            raise DSLValidationError(
                "Cannot publish: graph must contain Start + at least one downstream node"
            )
        wf.version += 1
        wf.status = "published"
        wf.published_graph_data = dict(wf.graph_data)
        version_row = WorkflowVersion(
            workflow_id=wf.id,
            version=wf.version,
            graph_data=wf.published_graph_data,
            published_by=user_id,
            published_at=datetime.now(timezone.utc),
            change_note=change_note,
        )
        self.db.add(version_row)
        await self.db.flush()
        await self._prune_old_versions(wf.id)
        await self.db.refresh(wf)
        return wf

    async def revert_to_draft(self, wf_id: uuid.UUID) -> Workflow:
        wf = await self.get(wf_id)
        wf.status = "draft"
        await self.db.flush()
        await self.db.refresh(wf)
        return wf

    async def _prune_old_versions(self, wf_id: uuid.UUID, keep: int = 50) -> None:
        rows = await self.db.execute(
            select(WorkflowVersion.id)
            .where(WorkflowVersion.workflow_id == wf_id)
            .order_by(desc(WorkflowVersion.version))
            .offset(keep)
        )
        to_delete = list(rows.scalars().all())
        for old_id in to_delete:
            obj = await self.db.get(WorkflowVersion, old_id)
            if obj is not None:
                await self.db.delete(obj)
        if to_delete:
            await self.db.flush()
