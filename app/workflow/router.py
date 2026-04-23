"""Workflow HTTP routes. GET for reads, POST for everything else (RPC-style).

Mutations use `/xxx/update` / `/xxx/delete`. Execution lifecycle:
  POST  /{wf_id}/run                             — kick off (202 Accepted)
  GET   /{wf_id}/executions                      — list
  GET   /{wf_id}/executions/{exec_id}            — detail incl. per-node status
  POST  /{wf_id}/executions/{exec_id}/cancel     — best-effort cancel
"""
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, check_resource_access
from app.auth.models import User
from app.core.database import get_db
from app.workflow.dsl import DSLValidationError
from app.workflow.cancel_bus import publish_cancel
from app.workflow.events import EventBus
from app.workflow.execution_service import ExecutionService, WorkflowNotPublished
from app.workflow.models import NodeExecution, WorkflowExecution
from app.workflow.schemas import (
    WorkflowCreate,
    WorkflowPublishRequest,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowUpdate,
)
from app.workflow.service import WorkflowNotFound, WorkflowService
from app.workflow.templates_service import TemplateNotFound, TemplatesService
from app.workflow.version_service import VersionNotFound, VersionService
from app.workflow.webhook_service import WebhookNotConfigured, WebhookService


# Per-process handles for live executions. Lost on restart — plan 20 replaces
# this with a durable cancellation registry that works across workers.
_live_buses: dict[uuid.UUID, EventBus] = {}
_live_tasks: dict[uuid.UUID, asyncio.Task] = {}

router = APIRouter(prefix="/workflow", tags=["workflow"])


async def _load_and_authorize(
    wf_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    required_level: str = "edit",
):
    """Fetch + department-scoped access check. Reused by all mutating routes."""
    svc = WorkflowService(db)
    try:
        wf = await svc.get(wf_id)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    await check_resource_access(
        user, "workflow", wf.id, db, wf.created_by, required_level=required_level
    )
    return svc, wf


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowCreate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = WorkflowService(db)
    try:
        return await svc.create(data, user.id, owner_agent_id=data.owner_agent_id)
    except DSLValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid DSL: {e}")


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    owner_agent_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).list(
        page=page, page_size=page_size, owner_agent_id=owner_agent_id,
    )


@router.get("/{wf_id}", response_model=WorkflowResponse)
async def get_workflow(
    wf_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    try:
        wf = await WorkflowService(db).get(wf_id)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    # Department-scoped access control, same pattern as KB in plans 4/6.
    await check_resource_access(user, "workflow", wf.id, db, wf.created_by)
    return wf


@router.post("/{wf_id}/update", response_model=WorkflowResponse)
async def update_workflow(
    wf_id: uuid.UUID,
    data: WorkflowUpdate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc, _ = await _load_and_authorize(wf_id, user, db)
    try:
        return await svc.update(wf_id, data)
    except DSLValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid DSL: {e}")


@router.post("/{wf_id}/delete", status_code=status.HTTP_200_OK)
async def delete_workflow(
    wf_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc, _ = await _load_and_authorize(wf_id, user, db)
    await svc.delete(wf_id)
    return {"ok": True}


@router.post("/{wf_id}/publish", response_model=WorkflowResponse)
async def publish_workflow(
    wf_id: uuid.UUID,
    body: WorkflowPublishRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc, _ = await _load_and_authorize(wf_id, user, db)
    try:
        return await svc.publish(wf_id, user.id, body.change_note)
    except DSLValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid DSL: {e}")


@router.post("/{wf_id}/draft", response_model=WorkflowResponse)
async def revert_to_draft(
    wf_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc, _ = await _load_and_authorize(wf_id, user, db)
    return await svc.revert_to_draft(wf_id)


# ---------------- Execution lifecycle ----------------------------------------


@router.post("/{wf_id}/run", status_code=202)
async def run_workflow(
    wf_id: uuid.UUID,
    body: WorkflowRunRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Kick off an execution. Returns `execution_id` for subsequent polling /
    WS subscription. Long-running workflows should be offloaded to Celery
    (plan 20) — Phase 1b initial cut runs inline for short executions."""
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="use")
    svc = ExecutionService(db)
    try:
        exec_row = await svc.create_execution(
            wf_id, user.id, body.inputs, from_draft=body.from_draft,
        )
    except WorkflowNotPublished:
        raise HTTPException(400, "Workflow has no published version")

    # Commit NOW so the background task's independent session can see the
    # newly-created row. Postgres READ COMMITTED isolates uncommitted writes
    # across sessions; without this commit, the task would `db.get(...)` and
    # find nothing.
    await db.commit()

    exec_id = exec_row.id
    bus = EventBus()
    _live_buses[exec_id] = bus
    task = asyncio.create_task(_run_and_cleanup(exec_id, bus))
    _live_tasks[exec_id] = task
    return {"execution_id": str(exec_id)}


async def _run_and_cleanup(exec_id: uuid.UUID, bus: EventBus) -> None:
    """Background driver — opens its OWN session. The request session that
    created the execution row has already committed + closed by the time
    this coroutine gets scheduled (FastAPI's `get_db` dependency closes the
    session when the handler returns; reusing it here would crash with
    'session is in prepared state; no further SQL')."""
    from app.core.database import async_session
    try:
        async with async_session() as bg_db:
            exec_row = await bg_db.get(WorkflowExecution, exec_id)
            if exec_row is None:
                return
            svc = ExecutionService(bg_db)
            await svc.run_and_persist(exec_row, bus)
            await bg_db.commit()
    except Exception:  # noqa: BLE001
        import structlog
        structlog.get_logger(__name__).exception(
            "workflow_background_run_failed", execution_id=str(exec_id),
        )
    finally:
        _live_tasks.pop(exec_id, None)
        # Keep the bus around 60s so a WS that connects AFTER the scheduler
        # already finished still gets the replayed history. Fast-fail workflows
        # used to appear as silence to the UI because the bus closed + got
        # pop'd before the client managed to upgrade.
        asyncio.create_task(_delayed_bus_pop(exec_id, 60.0))


async def _delayed_bus_pop(exec_id: uuid.UUID, after: float) -> None:
    try:
        await asyncio.sleep(after)
    finally:
        _live_buses.pop(exec_id, None)


@router.get("/{wf_id}/executions")
async def list_executions(
    wf_id: uuid.UUID,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="use")
    rows = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == wf_id)
        .order_by(desc(WorkflowExecution.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "error": r.error,
        }
        for r in rows.scalars().all()
    ]


@router.get("/{wf_id}/executions/{exec_id}")
async def get_execution(
    wf_id: uuid.UUID,
    exec_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="use")
    exec_row = await db.get(WorkflowExecution, exec_id)
    if exec_row is None or exec_row.workflow_id != wf_id:
        raise HTTPException(404, "Execution not found")
    node_rows = await db.execute(
        select(NodeExecution).where(NodeExecution.execution_id == exec_id)
    )
    return {
        "id": str(exec_row.id),
        "status": exec_row.status,
        "output": exec_row.output,
        "error": exec_row.error,
        "started_at": exec_row.started_at,
        "finished_at": exec_row.finished_at,
        "nodes": [
            {
                "node_id": n.node_id,
                "type": n.node_type,
                "status": n.status,
                "input": n.input_data,
                "output": n.output_data,
                "error": n.error,
            }
            for n in node_rows.scalars().all()
        ],
    }


from pydantic import BaseModel as _BaseModel, ConfigDict as _ConfigDict


class ResumeRequest(_BaseModel):
    """HITL resume payload — arbitrary JSON-serializable value handed back
    to ``interrupt()`` inside the paused node."""
    model_config = _ConfigDict(extra="forbid")
    value: object = None


@router.post("/{wf_id}/executions/{exec_id}/resume", status_code=202)
async def resume_execution(
    wf_id: uuid.UUID,
    exec_id: uuid.UUID,
    body: ResumeRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Resume a waiting (HITL-paused) execution with the supplied value.

    The frontend gets ``waiting_input`` via WS when the graph hits a
    ``human_approval`` node; after the user decides, it POSTs here. We
    re-enter ``compiled.ainvoke(Command(resume=value))`` under the same
    thread_id, streaming new events to a fresh EventBus that the frontend
    re-subscribes via the normal ``/events`` WS endpoint.
    """
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="use")

    row = await db.get(WorkflowExecution, exec_id)
    if row is None or row.workflow_id != wf_id:
        raise HTTPException(404, "Execution not found")
    if row.status != "waiting":
        raise HTTPException(
            400, f"Execution is not waiting (current status: {row.status})"
        )

    # Commit so the background task's independent session sees the row.
    await db.commit()

    bus = EventBus()
    _live_buses[exec_id] = bus
    asyncio.create_task(_resume_and_cleanup(exec_id, bus, body.value))
    return {"execution_id": str(exec_id)}


async def _resume_and_cleanup(exec_id: uuid.UUID, bus: EventBus, resume_value) -> None:
    """Background driver for resume — mirrors ``_run_and_cleanup`` but calls
    ``ExecutionService.resume_execution`` instead of ``run_and_persist``."""
    from app.core.database import async_session
    try:
        async with async_session() as bg_db:
            exec_row = await bg_db.get(WorkflowExecution, exec_id)
            if exec_row is None:
                return
            svc = ExecutionService(bg_db)
            await svc.resume_execution(exec_row, bus, resume_value)
            await bg_db.commit()
    except Exception:  # noqa: BLE001
        import structlog
        structlog.get_logger(__name__).exception(
            "workflow_resume_failed", execution_id=str(exec_id),
        )
    finally:
        asyncio.create_task(_delayed_bus_pop(exec_id, 60.0))


@router.post("/{wf_id}/executions/{exec_id}/cancel", status_code=200)
async def cancel_execution(
    wf_id: uuid.UUID,
    exec_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Best-effort: cancel if scheduler is live in THIS worker, and always
    update DB status so the UI reflects intent. Multi-worker proper
    cancellation (pub/sub fanout) lands in plan 20."""
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="use")

    row = await db.get(WorkflowExecution, exec_id)
    if row is None or row.workflow_id != wf_id:
        raise HTTPException(404, "Execution not found")

    task = _live_tasks.get(exec_id)
    if task is not None and not task.done():
        task.cancel()

    if row.status in ("pending", "running"):
        row.status = "cancelled"
        row.finished_at = datetime.now(timezone.utc)
        await db.flush()

    # Fan out to other workers — best-effort, never fatal.
    await publish_cancel(exec_id)

    return {"ok": True, "scheduler_reachable": task is not None}


# ---------------- Version history ----------------


@router.get("/{wf_id}/versions")
async def list_versions(
    wf_id: uuid.UUID,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="view")
    vs = await VersionService(db).list_versions(wf_id, page=page, page_size=page_size)
    return [
        {
            "version": v.version,
            "published_at": v.published_at,
            "published_by": str(v.published_by) if v.published_by else None,
            "change_note": v.change_note,
        }
        for v in vs
    ]


@router.get("/{wf_id}/versions/{version}")
async def get_version(
    wf_id: uuid.UUID,
    version: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="view")
    try:
        v = await VersionService(db).get_version(wf_id, version)
    except VersionNotFound:
        raise HTTPException(404, "Version not found")
    return {
        "version": v.version,
        "graph_data": v.graph_data,
        "published_at": v.published_at,
        "change_note": v.change_note,
    }


@router.post("/{wf_id}/versions/{version}/rollback", response_model=WorkflowResponse)
async def rollback_version(
    wf_id: uuid.UUID,
    version: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db)
    try:
        return await VersionService(db).rollback_to_draft(wf_id, version)
    except VersionNotFound:
        raise HTTPException(404, "Version not found")


# ---------------- Templates ----------------


class _TemplateSaveRequest(__import__("pydantic").BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    description: str | None = None
    category: str = "general"


class _TemplateCreateRequest(__import__("pydantic").BaseModel):
    model_config = {"extra": "forbid"}
    name: str


@router.post("/{wf_id}/save-as-template", status_code=201)
async def save_as_template(
    wf_id: uuid.UUID,
    body: _TemplateSaveRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="view")
    svc = TemplatesService(db)
    try:
        tpl = await svc.save_from_workflow(
            wf_id, user.id,
            name=body.name, description=body.description, category=body.category,
        )
    except TemplateNotFound:
        raise HTTPException(404, "Workflow not found")
    return {"id": str(tpl.id), "name": tpl.name, "category": tpl.category}


@router.get("/templates")
async def list_templates(
    user: CurrentUser,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    tpls = await TemplatesService(db).list_templates(category=category)
    return [
        {
            "id": str(t.id), "name": t.name, "description": t.description,
            "category": t.category, "is_builtin": t.is_builtin,
            "created_at": t.created_at,
        }
        for t in tpls
    ]


@router.get("/templates/{tpl_id}")
async def get_template(
    tpl_id: uuid.UUID, user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    try:
        t = await TemplatesService(db).get_template(tpl_id)
    except TemplateNotFound:
        raise HTTPException(404, "Template not found")
    return {
        "id": str(t.id), "name": t.name, "description": t.description,
        "category": t.category, "graph_data": t.graph_data,
        "is_builtin": t.is_builtin,
    }


@router.post("/templates/{tpl_id}/create", response_model=WorkflowResponse, status_code=201)
async def create_from_template(
    tpl_id: uuid.UUID,
    body: _TemplateCreateRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await TemplatesService(db).create_workflow_from_template(
            tpl_id, user.id, name=body.name,
        )
    except TemplateNotFound:
        raise HTTPException(404, "Template not found")


@router.post("/templates/{tpl_id}/delete", status_code=200)
async def delete_template(
    tpl_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = TemplatesService(db)
    try:
        await svc.delete_template(tpl_id)
    except TemplateNotFound:
        raise HTTPException(404, "Template not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/{wf_id}/duplicate", response_model=WorkflowResponse, status_code=201)
async def duplicate_workflow(
    wf_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db, required_level="view")
    try:
        return await TemplatesService(db).duplicate_workflow(wf_id, user.id)
    except TemplateNotFound:
        raise HTTPException(404, "Workflow not found")


# ---------------- Webhook management ----------------


class _WebhookRegenerateRequest(__import__("pydantic").BaseModel):
    model_config = {"extra": "forbid"}
    auth_type: str = "hmac"  # "none" | "bearer" | "hmac"


class _WebhookConfigUpdate(__import__("pydantic").BaseModel):
    model_config = {"extra": "forbid"}
    auth_type: str | None = None
    allowed_ips: list[str] | None = None


@router.post("/{wf_id}/webhook/regenerate")
async def regenerate_webhook(
    wf_id: uuid.UUID,
    body: _WebhookRegenerateRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db)
    if body.auth_type not in ("none", "bearer", "hmac"):
        raise HTTPException(400, "auth_type must be one of none/bearer/hmac")
    try:
        cfg = await WebhookService(db).regenerate(wf_id, auth_type=body.auth_type)
    except WebhookNotConfigured:
        raise HTTPException(404, "Workflow not found")
    # Return the full config including secret ONCE on regeneration — UI must
    # show-and-forget; subsequent reads return a redacted view.
    return cfg


@router.post("/{wf_id}/webhook/config/update")
async def update_webhook_config(
    wf_id: uuid.UUID,
    body: _WebhookConfigUpdate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db)
    try:
        cfg = await WebhookService(db).update_config(
            wf_id, body.model_dump(exclude_none=True)
        )
    except WebhookNotConfigured:
        raise HTTPException(404, "Workflow not found")
    redacted = dict(cfg)
    if "secret" in redacted:
        redacted["secret"] = "<redacted>"
    return redacted


@router.post("/{wf_id}/webhook/delete")
async def delete_webhook(
    wf_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _, _ = await _load_and_authorize(wf_id, user, db)
    try:
        await WebhookService(db).delete(wf_id)
    except WebhookNotConfigured:
        raise HTTPException(404, "Workflow not found")
    return {"ok": True}
