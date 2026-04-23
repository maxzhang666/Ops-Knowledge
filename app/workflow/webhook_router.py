"""Public webhook entry point — external systems trigger workflow executions.

No JWT auth (caller has the HMAC secret or bearer token, not a user account).
Rate-limited via 1a SlowAPI to 60 req/min per hook. IP allowlist + HMAC /
bearer authentication enforced by WebhookService.verify.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limiter import limiter
from app.workflow.events import EventBus
from app.workflow.execution_service import ExecutionService, WorkflowNotPublished
from app.workflow.router import _live_buses, _run_and_cleanup
from app.workflow.webhook_service import WebhookAuthFailed, WebhookService

router = APIRouter(prefix="/webhook", tags=["workflow-webhook"])


@router.post("/{hook_id}", status_code=202)
@limiter.limit("60/minute")
async def trigger_webhook(
    request: Request,
    hook_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = WebhookService(db)
    wf = await svc.find_by_hook_id(hook_id)
    if wf is None:
        raise HTTPException(404, "Unknown hook")

    raw_body = await request.body()
    try:
        WebhookService.verify(
            wf.webhook_config or {},
            headers={k.lower(): v for k, v in request.headers.items()},
            raw_body=raw_body,
            client_ip=request.client.host if request.client else "",
        )
    except WebhookAuthFailed as e:
        raise HTTPException(status_code=401, detail=str(e))

    try:
        inputs = json.loads(raw_body) if raw_body else {}
    except Exception:
        inputs = {"raw": raw_body.decode("utf-8", errors="replace")}

    exec_svc = ExecutionService(db)
    try:
        exec_row = await exec_svc.create_execution(wf.id, None, inputs)
    except WorkflowNotPublished:
        raise HTTPException(400, "Workflow has no published version")

    # Commit so the background task's own session sees the row.
    await db.commit()

    exec_id = exec_row.id
    bus = EventBus()
    _live_buses[exec_id] = bus
    asyncio.create_task(_run_and_cleanup(exec_id, bus))
    return {"execution_id": str(exec_id)}
