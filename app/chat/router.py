import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentService
from app.auth.dependencies import CurrentUser, check_resource_access
from app.core.limiter import limiter
from app.chat.pipeline import run_rag_pipeline
from app.chat.schemas import ChatRequest, ConversationResponse, ConversationUpdate, MessageResponse
from app.chat.service import ConversationService
from app.chat.streaming import stream_chat_response
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/agents/{agent_id}", tags=["chat"])


@router.get("/conversations", response_model=PaginatedResponse)
async def list_conversations(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # Verify agent access
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    items, total = await svc.list_conversations(
        agent_id, current_user.id, pagination.offset, pagination.page_size
    )
    return PaginatedResponse(
        items=[ConversationResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.create_conversation(agent_id, current_user.id)
    return conv


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max messages to return"),
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id)
    if conv.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cannot access another user's conversation")
    messages = await svc.get_messages(conv.id, offset=offset, limit=limit)
    return [MessageResponse.model_validate(m) for m in messages]


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    format: str = Query("markdown", regex="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """Spec 22.6 — export a conversation as Markdown (human-readable) or JSON
    (full metadata). Keeps the server in control of format so all clients look
    identical (frontend download button → same file regardless of browser)."""
    from datetime import datetime
    import json as _json
    from fastapi.responses import Response

    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id)
    if conv.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cannot access another user's conversation")

    # Pull all messages (paginated limit is API-level; export wants full history)
    all_msgs: list = []
    offset = 0
    while True:
        batch = await svc.get_messages(conv.id, offset=offset, limit=200)
        if not batch:
            break
        all_msgs.extend(batch)
        if len(batch) < 200:
            break
        offset += 200

    title = conv.title or "新对话"
    safe_name = "".join(c for c in title if c.isalnum() or c in " -_.") or "conversation"

    if format == "json":
        payload = {
            "conversation_id": str(conv.id),
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "title": title,
            "created_at": conv.created_at.isoformat(),
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                    "token_usage": m.token_usage,
                    "metadata": m.metadata_,
                }
                for m in all_msgs
            ],
        }
        body = _json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'},
        )

    # Markdown format — include references when present in metadata
    lines = [f"# {title}", ""]
    lines.append(f"- Agent: {agent.name}")
    lines.append(f"- 导出时间: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    for m in all_msgs:
        role_label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(m.role, m.role)
        lines.append(f"## {role_label}")
        lines.append(f"<sub>{m.created_at.isoformat()}</sub>")
        lines.append("")
        lines.append(m.content or "")
        meta = m.metadata_ or {}
        cited = meta.get("cited_sources") or []
        if cited:
            lines.append("")
            lines.append("**引用**")
            for c in cited:
                lines.append(f"- [{c.get('index')}] {c.get('title', '')}")
        lines.append("")
    body = "\n".join(lines).encode("utf-8")
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
    )


@router.get(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=MessageResponse,
)
async def get_message(
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    await svc.get_conversation(conversation_id)
    msg = await svc.get_message(message_id)
    return MessageResponse.model_validate(msg)


@router.post("/conversations/{conversation_id}/update", response_model=ConversationResponse)
async def update_conversation(
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    data: ConversationUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id)
    if conv.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cannot update another user's conversation")

    updates = data.model_dump(exclude_unset=True)
    conv = await svc.update_conversation(conversation_id, **updates)
    return conv


@router.post(
    "/conversations/{conversation_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id)
    if conv.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cannot delete another user's conversation")
    await svc.delete_conversation(conversation_id)


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    agent_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Unified chat endpoint — spec 22.5 four calling modes:
      - ``async=true`` + ``callback_url`` → Async Callback (202 + POST result)
      - ``async=true`` (no callback)      → Async Polling  (202 + poll /messages/{id})
      - ``Accept: text/event-stream``     → Sync SSE (default for browsers)
      - ``Accept: application/json``      → Sync Blocking (return JSON when done)
    """
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    if body.async_mode:
        return await _start_async_chat(
            agent=agent, body=body, user_id=current_user.id,
            callback_url=body.callback_url,
        )

    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" not in accept:
        return await _sync_blocking_chat(agent=agent, body=body, user_id=current_user.id)

    pipeline = run_rag_pipeline(
        agent=agent,
        query=body.content,
        conversation_id=body.conversation_id,
        user_id=current_user.id,
    )
    return StreamingResponse(
        stream_chat_response(pipeline),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _sync_blocking_chat(*, agent, body: ChatRequest, user_id):
    """Drain the pipeline and return the final answer as JSON."""
    from fastapi.responses import JSONResponse
    pipeline = run_rag_pipeline(
        agent=agent, query=body.content,
        conversation_id=body.conversation_id, user_id=user_id,
    )
    answer = ""
    conversation_id = None
    message_id = None
    token_usage: dict = {}
    cited_chunks: list = []
    async for ev_type, data in pipeline:
        if ev_type == "message_start" and isinstance(data, dict):
            conversation_id = data.get("conversation_id")
            message_id = data.get("message_id")
        elif ev_type == "content_delta" and isinstance(data, dict):
            answer += data.get("delta", "")
        elif ev_type == "retrieval_info" and isinstance(data, dict):
            cited_chunks = data.get("chunks", [])
        elif ev_type == "message_end" and isinstance(data, dict):
            token_usage = data.get("token_usage", {}) or {}
    return JSONResponse({
        "conversation_id": conversation_id,
        "message_id": message_id,
        "answer": answer,
        "token_usage": token_usage,
        "references": cited_chunks,
    })


async def _start_async_chat(*, agent, body: ChatRequest, user_id, callback_url: str | None):
    """202 Accepted — drains pipeline in a background asyncio task. Message row
    is created immediately so clients can poll /messages/{id} for status +
    final content. If callback_url is given, POST the result when done.
    """
    import asyncio
    from fastapi.responses import JSONResponse

    async def _run():
        pipeline = run_rag_pipeline(
            agent=agent, query=body.content,
            conversation_id=body.conversation_id, user_id=user_id,
        )
        answer = ""
        message_id = None
        async for ev_type, data in pipeline:
            if ev_type == "message_start" and isinstance(data, dict):
                message_id = data.get("message_id")
            elif ev_type == "content_delta" and isinstance(data, dict):
                answer += data.get("delta", "")
        if callback_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as cli:
                    await cli.post(callback_url, json={
                        "message_id": message_id,
                        "answer": answer,
                    })
            except Exception:
                pass  # callback is best-effort

    asyncio.create_task(_run())
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "hint": (
                f"Result will be POSTed to {callback_url}" if callback_url
                else "Poll GET /agents/{agent_id}/conversations/{conv_id}/messages/{msg_id}"
            ),
        },
    )
