"""WebSocket stream of execution events. JWT via `?token=` — browsers can't
attach Authorization headers to WebSocket handshakes. Token is validated
BEFORE accept() so unauthenticated clients never get an open socket."""
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import authenticate_ws_token, check_resource_access
from app.core.database import get_db
from app.workflow.models import Workflow, WorkflowExecution
from app.workflow.router import _live_buses

router = APIRouter(prefix="/workflow", tags=["workflow-events"])


@router.websocket("/{wf_id}/executions/{exec_id}/events")
async def events_ws(
    ws: WebSocket,
    wf_id: uuid.UUID,
    exec_id: uuid.UUID,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # 1. Authenticate — close 4401 BEFORE accept() if invalid.
    try:
        user = await authenticate_ws_token(token, db)
    except Exception:
        await ws.close(code=4401)
        return

    # 2. Authorize — execution must belong to a workflow the user can access.
    exec_row = await db.get(WorkflowExecution, exec_id)
    if exec_row is None or exec_row.workflow_id != wf_id:
        await ws.close(code=4404)
        return
    wf = await db.get(Workflow, wf_id)
    if wf is None:
        await ws.close(code=4404)
        return
    try:
        await check_resource_access(
            user, "workflow", wf.id, db, wf.created_by, required_level="use"
        )
    except Exception:
        await ws.close(code=4403)
        return

    await ws.accept()
    bus = _live_buses.get(exec_id)
    if bus is None:
        await ws.send_json({"type": "error", "data": {"msg": "execution not live"}})
        await ws.close()
        return

    q = bus.subscribe()
    try:
        async for ev in bus.stream(q):
            await ws.send_json({
                "type": ev.type,
                "node_id": ev.node_id,
                "data": ev.data,
                "ts": ev.ts.isoformat(),
            })
    except WebSocketDisconnect:
        return
