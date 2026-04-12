import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentService
from app.auth.dependencies import CurrentUser, check_resource_access
from app.chat.pipeline import run_rag_pipeline
from app.chat.schemas import ChatRequest, ConversationResponse, MessageResponse
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
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id)
    messages = await svc.get_messages(conv.id)
    return [MessageResponse.model_validate(m) for m in messages]


@router.delete(
    "/conversations/{conversation_id}",
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
async def chat(
    agent_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    agent_svc = AgentService(db)
    agent = await agent_svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

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
